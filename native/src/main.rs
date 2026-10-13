#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod printer;
mod render;
use serde_json::{json, Value};
use std::{
    collections::VecDeque,
    fs,
    path::{Path, PathBuf},
    sync::Mutex,
    time::{Duration, Instant},
};
use tauri::Manager;
use uuid::Uuid;
struct Job {
    id: String,
    created: Instant,
    raster: Vec<u8>,
}
struct AppState {
    directory: PathBuf,
    downloads: PathBuf,
    jobs: Mutex<VecDeque<Job>>,
    hardware: tokio::sync::Mutex<()>,
    files: Mutex<()>,
}
fn defaults() -> Value {
    serde_json::from_str(include_str!("../defaults.json")).unwrap()
}
fn read(path: &Path) -> Result<Value, String> {
    if !path.exists() {
        return Ok(json!({}));
    }
    serde_json::from_slice(&fs::read(path).map_err(|e| e.to_string())?)
        .map_err(|e| format!("Cannot read {}: {e}", path.display()))
}
fn atomic(path: &Path, value: &Value) -> Result<(), String> {
    fs::create_dir_all(path.parent().ok_or("Invalid settings path")?).map_err(|e| e.to_string())?;
    let tmp = path.with_extension(format!("{}.tmp", Uuid::new_v4()));
    fs::write(
        &tmp,
        serde_json::to_vec_pretty(value).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    if let Err(e) = fs::rename(&tmp, path) {
        let _ = fs::remove_file(tmp);
        return Err(e.to_string());
    }
    Ok(())
}
fn validate_presets(value: &Value) -> Result<(), String> {
    let map = value.as_object().ok_or("Presets must be a JSON object")?;
    for (name, preset) in map {
        if name.trim().is_empty() || name.chars().count() > 80 || defaults().get(name).is_some() {
            return Err(
                "Use a personal name different from the two defaults (1–80 characters).".into(),
            );
        }
        if !["paragraph", "cable", "image"].contains(&preset["kind"].as_str().unwrap_or(""))
            || !preset["settings"].is_object()
        {
            return Err(format!("Invalid preset: {name}"));
        }
    }
    Ok(())
}
impl AppState {
    fn take_job(&self, id: &str) -> Result<Vec<u8>, String> {
        let mut jobs = self
            .jobs
            .lock()
            .map_err(|_| "Preview storage unavailable")?;
        let i = jobs
            .iter()
            .position(|j| j.id == id)
            .ok_or("Preview expired or already sent. Refresh before printing.")?;
        let job = jobs.remove(i).unwrap();
        if job.created.elapsed() > Duration::from_secs(3600) {
            return Err("Preview expired; refresh it.".into());
        }
        Ok(job.raster)
    }
    fn init(&self) -> Result<Value, String> {
        let _lock = self.files.lock().map_err(|_| "Settings unavailable")?;
        let mut warning = String::new();
        let personal = match read(&self.directory.join("my-presets.json")).and_then(|p| {
            validate_presets(&p)?;
            Ok(p)
        }) {
            Ok(p) => p,
            Err(e) => {
                warning = e;
                json!({})
            }
        };
        let prefs = read(&self.directory.join("printer.json")).unwrap_or(json!({}));
        Ok(
            json!({"defaults":defaults(),"personal":personal,"address":prefs["address"].as_str().unwrap_or(""),"warning":warning,"native":true,"settings_directory":self.directory.to_string_lossy()}),
        )
    }
    fn save_address(&self, address: &str) -> Result<(), String> {
        if address.parse::<btleplug::api::BDAddr>().is_err() {
            return Err("Enter a valid printer Bluetooth address.".into());
        }
        let _lock = self.files.lock().map_err(|_| "Settings unavailable")?;
        atomic(
            &self.directory.join("printer.json"),
            &json!({"address":address}),
        )
    }
}
#[tauri::command]
async fn api(
    path: String,
    data: Value,
    state: tauri::State<'_, AppState>,
) -> Result<Value, String> {
    match path.as_str() {
        "init" => state.init(),
        "preview" => {
            let rendered = tauri::async_runtime::spawn_blocking(move || render::render(&data))
                .await
                .map_err(|e| e.to_string())??;
            let id = Uuid::new_v4().to_string();
            let mut meta = rendered.meta;
            meta["job"] = json!(id);
            let mut jobs = state
                .jobs
                .lock()
                .map_err(|_| "Preview storage unavailable")?;
            jobs.push_back(Job {
                id,
                created: Instant::now(),
                raster: rendered.raster,
            });
            while jobs.len() > 12 {
                jobs.pop_front();
            }
            Ok(meta)
        }
        "print" => {
            let address = data["address"].as_str().unwrap_or("").trim();
            state.save_address(address)?;
            let _hardware = state
                .hardware
                .try_lock()
                .map_err(|_| "Printer is busy; wait for the current operation.")?;
            let raster = state.take_job(data["job"].as_str().unwrap_or(""))?;
            printer::send(address, &raster).await
        }
        "status" => {
            let address = data["address"].as_str().unwrap_or("").trim();
            state.save_address(address)?;
            let _hardware = state.hardware.try_lock().map_err(|_| "Printer is busy")?;
            printer::status(address).await
        }
        "discover" => {
            let _hardware = state.hardware.try_lock().map_err(|_| "Printer is busy")?;
            printer::discover().await
        }
        "preset" => {
            let _lock = state.files.lock().map_err(|_| "Settings unavailable")?;
            let name = data["name"].as_str().unwrap_or("").trim();
            let mut incoming = json!({});
            incoming[name] = json!({"kind":data["kind"],"settings":data["settings"]});
            validate_presets(&incoming)?;
            let file = state.directory.join("my-presets.json");
            let mut personal = read(&file)?;
            validate_presets(&personal)?;
            personal
                .as_object_mut()
                .unwrap()
                .extend(incoming.as_object().unwrap().clone());
            atomic(&file, &personal)?;
            Ok(json!({"personal":personal}))
        }
        "import-presets" => {
            let _lock = state.files.lock().map_err(|_| "Settings unavailable")?;
            validate_presets(&data)?;
            let file = state.directory.join("my-presets.json");
            let mut personal = read(&file)?;
            validate_presets(&personal)?;
            for (k, v) in data.as_object().unwrap() {
                if personal.get(k).is_some() {
                    return Err(format!(
                        "Preset '{k}' already exists. Rename it before importing."
                    ));
                }
                personal[k] = v.clone();
            }
            atomic(&file, &personal)?;
            Ok(json!({"personal":personal}))
        }
        "export-presets" => {
            let _lock = state.files.lock().map_err(|_| "Settings unavailable")?;
            let personal = read(&state.directory.join("my-presets.json"))?;
            validate_presets(&personal)?;
            let file = state
                .downloads
                .join(format!("Thermy9-presets-{}.json", Uuid::new_v4()));
            atomic(&file, &personal)?;
            Ok(json!({"file":file.to_string_lossy()}))
        }
        _ => Err("Unknown app command".into()),
    }
}
fn migrate(directory: &Path) {
    let candidates = std::env::current_dir().ok().into_iter().chain(
        std::env::current_exe().ok().into_iter().flat_map(|p| {
            p.ancestors()
                .skip(1)
                .take(5)
                .map(Path::to_path_buf)
                .collect::<Vec<_>>()
        }),
    );
    for root in candidates {
        let config = root.join("config");
        let presets = directory.join("my-presets.json");
        if !presets.exists() {
            if let Ok(data) = read(&config.join("my-presets.json")) {
                if data.as_object().is_some_and(|o| !o.is_empty())
                    && validate_presets(&data).is_ok()
                {
                    let _ = atomic(&presets, &data);
                }
            }
        }
        let printer = directory.join("printer.json");
        if !printer.exists() {
            if let Ok(data) = read(&config.join("paperang.json")) {
                if let Some(address) = data["macaddress"].as_str() {
                    let _ = atomic(&printer, &json!({"address":address}));
                }
            }
        }
    }
}
fn cli() -> bool {
    let args = std::env::args().collect::<Vec<_>>();
    if args.get(1).map(String::as_str) == Some("--render-check") {
        let result = (|| -> Result<(), String> {
            let path = args.get(2).ok_or("Input JSON required")?;
            let output = args.get(3).ok_or("Output prefix required")?;
            let data = read(Path::new(path))?;
            let rendered = render::render(&data)?;
            use base64::Engine;
            let png = base64::engine::general_purpose::STANDARD
                .decode(rendered.meta["preview_png"].as_str().unwrap())
                .map_err(|e| e.to_string())?;
            fs::write(format!("{output}.png"), png).map_err(|e| e.to_string())?;
            fs::write(format!("{output}.bin"), rendered.raster).map_err(|e| e.to_string())?;
            atomic(Path::new(&format!("{output}.json")), &rendered.meta)?;
            Ok(())
        })();
        if let Err(e) = result {
            eprintln!("{e}");
            std::process::exit(1);
        }
        return true;
    }
    if args.get(1).map(String::as_str) == Some("--status-check") {
        let address = args.get(2).cloned().unwrap_or_default();
        let output = args.get(3).cloned().unwrap_or("status.json".into());
        let result = tokio::runtime::Runtime::new()
            .unwrap()
            .block_on(printer::status(&address));
        let value = match result {
            Ok(v) => v,
            Err(e) => json!({"error":e}),
        };
        let _ = fs::write(output, serde_json::to_vec_pretty(&value).unwrap());
        return true;
    }
    false
}
fn main() {
    if cli() {
        return;
    }
    tauri::Builder::default()
        .setup(|app| {
            let directory = app.path().app_data_dir()?;
            fs::create_dir_all(&directory)?;
            migrate(&directory);
            app.manage(AppState {
                directory,
                downloads: app.path().download_dir()?,
                jobs: Mutex::new(VecDeque::new()),
                hardware: tokio::sync::Mutex::new(()),
                files: Mutex::new(()),
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if window.state::<AppState>().hardware.try_lock().is_err() {
                    api.prevent_close();
                    if let Some(webview) = window.get_webview_window("main") {
                        let _ = webview.eval("document.getElementById('message').textContent = 'Please wait for the printer operation to finish before closing.';");
                    }
                }
            }
        })
        .invoke_handler(tauri::generate_handler![api])
        .run(tauri::generate_context!())
        .expect("Could not start Thermy9");
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn consumed_job_cannot_print_twice() {
        let state = AppState {
            directory: PathBuf::new(),
            downloads: PathBuf::new(),
            jobs: Mutex::new(VecDeque::from([Job {
                id: "test".into(),
                created: Instant::now(),
                raster: vec![1; 72],
            }])),
            hardware: tokio::sync::Mutex::new(()),
            files: Mutex::new(()),
        };
        assert_eq!(state.take_job("test").unwrap(), vec![1; 72]);
        assert!(state.take_job("test").is_err());
    }
    #[test]
    fn validate_presets_rejects_bad_entries() {
        assert!(validate_presets(&json!({"Cable flags":{"kind":"cable","settings":{}}})).is_err());
        assert!(
            validate_presets(&json!({"Mine":{"kind":"cable","settings":{"columns":4}}})).is_ok()
        );
    }
}
