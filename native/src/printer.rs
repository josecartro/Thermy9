//! Paperang STX/ETX framing ported from the validated Python transport.
use btleplug::{
    api::{Central, Characteristic, Manager as _, Peripheral as _, ScanFilter, WriteType},
    platform::{Adapter, Manager, Peripheral},
};
use futures::StreamExt;
use serde_json::{json, Value};
use tokio::{
    sync::mpsc,
    time::{sleep, timeout, Duration},
};
use uuid::Uuid;

const WRITE: Uuid = Uuid::from_u128(0x49535343884143f4a8d4ecbe34729bb3);
const NOTIFY: Uuid = Uuid::from_u128(0x495353431e4d4bd9ba6123c647249616);
const REGISTER: [u8; 14] = [
    2, 24, 0, 4, 0, 0x21, 0x95, 0x76, 0x35, 0x1c, 0xdf, 0x44, 0x21, 3,
];
type R<T> = Result<T, String>;
pub fn pack(command: u8, payload: &[u8], index: u8) -> Vec<u8> {
    let mut p = vec![2, command, index];
    p.extend_from_slice(&(payload.len() as u16).to_le_bytes());
    p.extend_from_slice(payload);
    p.extend_from_slice(&crc32fast::hash(payload).to_le_bytes());
    p.push(3);
    p
}
pub fn extract(buffer: &mut Vec<u8>) -> R<Vec<(u8, Vec<u8>)>> {
    let mut result = vec![];
    while !buffer.is_empty() {
        if buffer[0] != 2 {
            buffer.remove(0);
            continue;
        }
        if buffer.len() < 5 {
            break;
        }
        let len = u16::from_le_bytes([buffer[3], buffer[4]]) as usize;
        if len > 4096 {
            return Err("Invalid printer response length".into());
        }
        if buffer.len() < len + 10 {
            break;
        }
        let packet = buffer.drain(..len + 10).collect::<Vec<_>>();
        let data = packet[5..5 + len].to_vec();
        let crc = u32::from_le_bytes(packet[5 + len..9 + len].try_into().unwrap());
        if packet[len + 9] != 3 || crc != crc32fast::hash(&data) {
            return Err("Printer response failed its integrity check".into());
        }
        result.push((packet[1], data));
    }
    Ok(result)
}
async fn adapter() -> R<Adapter> {
    Manager::new()
        .await
        .map_err(|e| e.to_string())?
        .adapters()
        .await
        .map_err(|e| e.to_string())?
        .into_iter()
        .next()
        .ok_or("No Bluetooth adapter found. Enable Bluetooth and try again.".into())
}
pub async fn discover() -> R<Value> {
    let adapter = adapter().await?;
    adapter
        .start_scan(ScanFilter::default())
        .await
        .map_err(|e| e.to_string())?;
    sleep(Duration::from_secs(10)).await;
    let result = async {
        let mut devices = vec![];
        for p in adapter.peripherals().await.map_err(|e| e.to_string())? {
            if let Some(props) = p.properties().await.map_err(|e| e.to_string())? {
                let name = props.local_name.unwrap_or_default();
                if name.to_lowercase().contains("paperang")
                    || name.to_lowercase().contains("miaomiao")
                {
                    devices.push(
                        json!({"name":name,"address":p.address().to_string(),"transport":"BLE"}),
                    );
                }
            }
        }
        Ok(json!({"devices":devices}))
    }
    .await;
    let _ = adapter.stop_scan().await;
    result
}
async fn locate(address: &str) -> R<Peripheral> {
    let desired = address
        .parse::<btleplug::api::BDAddr>()
        .map_err(|_| "Enter a Bluetooth address such as AA:BB:CC:DD:EE:FF")?;
    let adapter = adapter().await?;
    adapter
        .start_scan(ScanFilter::default())
        .await
        .map_err(|e| e.to_string())?;
    let result = timeout(Duration::from_secs(20), async {
        loop {
            for p in adapter.peripherals().await.map_err(|e| e.to_string())? {
                if p.address() == desired {
                    return Ok(p);
                }
            }
            sleep(Duration::from_millis(250)).await;
        }
    })
    .await
    .unwrap_or_else(|_| {
        Err("Printer not found. Turn it on, keep it nearby and close other printer apps.".into())
    });
    let _ = adapter.stop_scan().await;
    result
}
struct Connection {
    peripheral: Peripheral,
    write: Characteristic,
    notifications: mpsc::UnboundedReceiver<R<(u8, Vec<u8>)>>,
    task: tokio::task::JoinHandle<()>,
}
impl Connection {
    async fn connect(address: &str) -> R<Self> {
        let peripheral = locate(address).await?;
        let connected = timeout(Duration::from_secs(20), peripheral.connect())
            .await
            .map_err(|_| "Bluetooth connection timed out")?
            .map_err(|e| e.to_string());
        if let Err(e) = connected {
            let _ = peripheral.disconnect().await;
            return Err(e);
        }
        let result = async {
            peripheral
                .discover_services()
                .await
                .map_err(|e| e.to_string())?;
            let chars = peripheral.characteristics();
            let write = chars
                .iter()
                .find(|c| c.uuid == WRITE)
                .cloned()
                .ok_or("Printer has no supported write service")?;
            let notify = chars
                .iter()
                .find(|c| c.uuid == NOTIFY)
                .cloned()
                .ok_or("Printer has no supported notification service")?;
            let mut stream = peripheral
                .notifications()
                .await
                .map_err(|e| e.to_string())?;
            peripheral
                .subscribe(&notify)
                .await
                .map_err(|e| e.to_string())?;
            let (tx, rx) = mpsc::unbounded_channel();
            let task = tokio::spawn(async move {
                let mut buffer = vec![];
                while let Some(event) = stream.next().await {
                    if event.uuid != NOTIFY {
                        continue;
                    }
                    buffer.extend(event.value);
                    match extract(&mut buffer) {
                        Ok(frames) => {
                            for frame in frames {
                                if tx.send(Ok(frame)).is_err() {
                                    return;
                                }
                            }
                        }
                        Err(e) => {
                            let _ = tx.send(Err(e));
                            return;
                        }
                    }
                }
            });
            Ok((write, rx, task))
        }
        .await;
        let (write, notifications, task) = match result {
            Ok(v) => v,
            Err(e) => {
                let _ = peripheral.disconnect().await;
                return Err(e);
            }
        };
        let mut c = Self {
            peripheral,
            write,
            notifications,
            task,
        };
        sleep(Duration::from_millis(200)).await;
        match c.request_raw(&REGISTER, 24).await {
            Ok(v) if v == [0] => Ok(c),
            other => {
                c.close().await;
                Err(other
                    .err()
                    .unwrap_or("Printer rejected protocol handshake".into()))
            }
        }
    }
    async fn write(&self, data: &[u8]) -> R<()> {
        // 20 bytes is valid even without a negotiated larger ATT MTU.
        for bytes in data.chunks(20) {
            timeout(
                Duration::from_secs(5),
                self.peripheral
                    .write(&self.write, bytes, WriteType::WithoutResponse),
            )
            .await
            .map_err(|_| "Bluetooth write timed out")?
            .map_err(|e| e.to_string())?;
            sleep(Duration::from_millis(10)).await;
        }
        Ok(())
    }
    async fn request_raw(&mut self, packet: &[u8], expected: u8) -> R<Vec<u8>> {
        while self.notifications.try_recv().is_ok() {}
        self.write(packet).await?;
        timeout(Duration::from_secs(4), async {
            while let Some(reply) = self.notifications.recv().await {
                let (command, data) = reply?;
                if command == expected {
                    return Ok(data);
                }
            }
            Err("Printer disconnected".into())
        })
        .await
        .map_err(|_| "Printer response timed out".to_string())?
    }
    async fn request(&mut self, command: u8) -> R<Vec<u8>> {
        self.request_raw(&pack(command, &[1], 0), command + 1).await
    }
    async fn close(&mut self) {
        self.task.abort();
        let _ = timeout(Duration::from_secs(3), self.peripheral.disconnect()).await;
    }
}
impl Drop for Connection {
    fn drop(&mut self) {
        self.task.abort();
    }
}
fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
async fn status_inner(address: &str) -> R<Value> {
    let mut c = Connection::connect(address).await?;
    let result=async {let battery=c.request(16).await?;let firmware=c.request(4).await?;let model=c.request(6).await?;let state=c.request(12).await?;Ok(json!({"address":address,"connected":true,"battery_percent":battery.first().copied().filter(|v|*v<=100),"firmware_version":firmware.iter().rev().map(u8::to_string).collect::<Vec<_>>().join("."),"model_code":hex(&model),"status_raw":hex(&state),"protocol":"Rust / Paperang BLE"}))}.await;
    c.close().await;
    result
}
pub async fn status(address: &str) -> R<Value> {
    timeout(Duration::from_secs(50), status_inner(address))
        .await
        .map_err(|_| {
            "Printer status timed out. Check that the printer is on and nearby.".to_string()
        })?
}
pub async fn send(address: &str, raster: &[u8]) -> R<Value> {
    if raster.is_empty() || raster.len() % 72 != 0 || raster.len() > 72 * 12000 {
        return Err("Invalid raster dimensions".into());
    }
    let mut c = Connection::connect(address).await?;
    let result = async {
        c.request(16).await?;
        for (command, value) in [(25, 75), (44, 0)] {
            c.write(&pack(command, &[value], 0)).await?;
            sleep(Duration::from_millis(200)).await;
        }
        for (i, chunk) in raster.chunks(1008).enumerate() {
            c.write(&pack(0, chunk, (i & 255) as u8)).await?;
        }
        sleep(Duration::from_millis(500)).await;
        c.request(16).await?;
        Ok(json!({"message":"One copy sent. Check the paper before printing another."}))
    }
    .await;
    c.close().await;
    result.map_err(|e: String| {
        format!("Print stopped: {e}. Check for a partial print before trying again.")
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn frames_and_corruption() {
        let packet = pack(17, &[100], 0);
        let mut partial = packet[..5].to_vec();
        assert!(extract(&mut partial).unwrap().is_empty());
        partial.extend_from_slice(&packet[5..]);
        assert_eq!(extract(&mut partial).unwrap(), vec![(17, vec![100])]);
        let mut bad = packet;
        bad[5] ^= 1;
        assert!(extract(&mut bad).is_err());
    }
    #[test]
    fn registration_is_exact() {
        assert_eq!(hex(&REGISTER), "0218000400219576351cdf442103");
    }
}
