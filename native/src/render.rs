use base64::{engine::general_purpose::STANDARD as B64, Engine};
use fontdue::{Font, FontSettings};
use image::{DynamicImage, GrayImage, ImageFormat, Luma};
use regex::Regex;
use serde_json::{json, Value};
use std::{io::Cursor, sync::OnceLock};

type R<T> = Result<T, String>;
const DOT_MM: f64 = 0.08472;
const FONT_BYTES: [&[u8]; 6] = [
    include_bytes!("../fonts/DejaVuSans.ttf"),
    include_bytes!("../fonts/DejaVuSans-Bold.ttf"),
    include_bytes!("../fonts/DejaVuSerif.ttf"),
    include_bytes!("../fonts/DejaVuSerif-Bold.ttf"),
    include_bytes!("../fonts/DejaVuSansMono.ttf"),
    include_bytes!("../fonts/DejaVuSansMono-Bold.ttf"),
];
pub fn n(s: &Value, k: &str, default: f64, min: f64, max: f64) -> R<f64> {
    let v = match s.get(k) {
        None => default,
        Some(v) => v
            .as_f64()
            .or_else(|| v.as_str().and_then(|v| v.parse().ok()))
            .ok_or_else(|| format!("Invalid {k}"))?,
    };
    if !v.is_finite() || v < min || v > max {
        return Err(format!("{k} must be between {min} and {max}."));
    }
    Ok(v)
}
fn b(s: &Value, k: &str, d: bool) -> bool {
    s.get(k).and_then(Value::as_bool).unwrap_or(d)
}
fn st<'a>(s: &'a Value, k: &str, d: &'a str) -> &'a str {
    s.get(k).and_then(Value::as_str).unwrap_or(d)
}
fn xml(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}
fn alignment(s: &str) -> R<&str> {
    if ["left", "center", "right"].contains(&s) {
        Ok(s)
    } else {
        Err("Invalid text alignment".into())
    }
}
fn offset(align: &str, area: f64, width: f64) -> f64 {
    match align {
        "center" => (area - width) / 2.,
        "right" => area - width,
        _ => 0.,
    }
}
struct Resources {
    fonts: Vec<Font>,
    options: resvg::usvg::Options<'static>,
    icons: Value,
}
fn resources() -> &'static Resources {
    static RES: OnceLock<Resources> = OnceLock::new();
    RES.get_or_init(|| {
        let mut options = resvg::usvg::Options::default();
        for bytes in FONT_BYTES {
            options.fontdb_mut().load_font_data(bytes.to_vec());
        }
        Resources {
            fonts: FONT_BYTES
                .iter()
                .map(|v| Font::from_bytes(*v, FontSettings::default()).expect("bundled font"))
                .collect(),
            options,
            icons: serde_json::from_str(include_str!("../../web/icons.json"))
                .expect("bundled icons"),
        }
    })
}
#[derive(Clone)]
struct Atom {
    svg: String,
    w: f64,
    h: f64,
    space: bool,
}
#[derive(Default)]
struct Line {
    atoms: Vec<Atom>,
    align: Option<String>,
}
impl Line {
    fn w(&self) -> f64 {
        self.atoms.iter().map(|a| a.w).sum()
    }
    fn h(&self, default: f64) -> f64 {
        self.atoms.iter().map(|a| a.h).fold(default / 2., f64::max)
    }
}
struct Block {
    lines: Vec<Line>,
    w: f64,
    h: f64,
    base: f64,
    gap: f64,
}
impl Block {
    fn paint(&self, x: f64, y: f64, area: f64, align: &str) -> String {
        let mut result = String::new();
        let mut yy = y;
        for line in &self.lines {
            let height = line.h(self.base);
            let mut xx = x + offset(line.align.as_deref().unwrap_or(align), area, line.w());
            for atom in &line.atoms {
                result += &format!(
                    "<g transform=\"translate({xx},{})\">{}</g>",
                    yy + (height - atom.h) / 2.,
                    atom.svg
                );
                xx += atom.w;
            }
            yy += height + self.gap;
        }
        result
    }
}
struct Rich {
    size: f64,
    bold: bool,
    family: usize,
    icon: f64,
    gap: f64,
}
impl Rich {
    fn new(s: &Value) -> R<Self> {
        let family = match st(s, "font_family", "sans") {
            "sans" => 0,
            "serif" => 2,
            "mono" => 4,
            _ => return Err("Invalid font family".into()),
        };
        Ok(Self {
            size: n(s, "font_size", 32., 8., 240.)?,
            bold: b(s, "bold", true),
            family,
            icon: n(s, "icon_size", 32., 8., 240.)?,
            gap: n(s, "line_gap", 4., 0., 100.)?,
        })
    }
    fn text(&self, text: &str, size: f64, bold: bool) -> Atom {
        let font = &resources().fonts[self.family + usize::from(bold)];
        let metrics = font.horizontal_line_metrics(size as f32).unwrap();
        let mut width = 0.;
        let mut prev = None;
        for ch in text.chars() {
            if let Some(p) = prev {
                width += font.horizontal_kern(p, ch, size as f32).unwrap_or(0.) as f64;
            }
            width += font.metrics(ch, size as f32).advance_width as f64;
            prev = Some(ch);
        }
        let family = ["DejaVu Sans", "DejaVu Serif", "DejaVu Sans Mono"][self.family / 2];
        let svg=format!("<text x=\"0\" y=\"{}\" font-family=\"{family}\" font-size=\"{size}\" font-weight=\"{}\" xml:space=\"preserve\" textLength=\"{width}\" lengthAdjust=\"spacingAndGlyphs\">{}</text>",metrics.ascent,if bold {"bold"} else {"normal"},xml(text));
        Atom {
            svg,
            w: width,
            h: (metrics.ascent - metrics.descent) as f64,
            space: text.trim().is_empty(),
        }
    }
    fn icon(&self, name: &str, size: f64) -> R<Atom> {
        if !(8. ..=240.).contains(&size) {
            return Err("Icon size must be 8–240 px".into());
        }
        let shapes = resources()
            .icons
            .get(name)
            .and_then(Value::as_array)
            .ok_or_else(|| format!("Unknown icon: {name}"))?;
        let mut svg = String::new();
        for shape in shapes {
            let a = shape.as_array().ok_or("Invalid icon data")?;
            let f = |i: usize| a[i].as_f64().unwrap_or(0.);
            svg+=&match a[0].as_str().unwrap_or("") {
                "circle"=>format!("<circle cx=\"{}\" cy=\"{}\" r=\"{}\"/>",f(1),f(2),f(3)),
                "rect"=>format!("<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\"/>",f(1),f(2),f(3),f(4)),
                "line"=>format!("<line x1=\"{}\" y1=\"{}\" x2=\"{}\" y2=\"{}\"/>",f(1),f(2),f(3),f(4)),
                "text"=>format!("<text x=\"{}\" y=\"{}\" font-size=\"{}\" font-family=\"DejaVu Sans\" font-weight=\"bold\" text-anchor=\"middle\" stroke=\"none\" fill=\"black\">{}</text>",f(1),f(2),f(3),xml(a[4].as_str().unwrap_or(""))),
                kind @ ("polygon"|"polyline")=>format!("<{kind} points=\"{}\"/>",a.iter().skip(1).map(Value::to_string).collect::<Vec<_>>().join(" ")),
                _=>return Err("Invalid icon primitive".into()),
            };
        }
        Ok(Atom{svg:format!("<svg width=\"{size}\" height=\"{size}\" viewBox=\"-1 -1 26 26\"><g fill=\"none\" stroke=\"black\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\">{svg}</g></svg>"),w:size,h:size,space:false})
    }
    fn layout(&self, text: &str, max: Option<f64>) -> R<Block> {
        static TOK: OnceLock<Regex> = OnceLock::new();
        static WORDS: OnceLock<Regex> = OnceLock::new();
        let tokens=TOK.get_or_init(||Regex::new(r"\[icon:[a-z0-9-]+(?::\d+)?\]|\[/?b\]|\[/?regular\]|\[size:\d+\]|\[/size\]|\[br\]|\[left\]|\[center\]|\[right\]|\n").unwrap());
        let words = WORDS.get_or_init(|| Regex::new(r"\s+|\S+").unwrap());
        let mut parts = vec![];
        let mut at = 0;
        for token in tokens.find_iter(text) {
            if token.start() > at {
                parts.push(&text[at..token.start()]);
            }
            parts.push(token.as_str());
            at = token.end();
        }
        if at < text.len() {
            parts.push(&text[at..]);
        }
        let mut lines = vec![];
        let mut line = Line::default();
        let mut sizes = vec![self.size];
        let mut bold = vec![self.bold];
        fn finish(lines: &mut Vec<Line>, line: &mut Line) {
            while line.atoms.last().is_some_and(|a| a.space) {
                line.atoms.pop();
            }
            lines.push(std::mem::take(line));
        }
        for part in parts {
            match part {
                "\n" | "[br]" => {
                    finish(&mut lines, &mut line);
                    continue;
                }
                "[left]" | "[center]" | "[right]" => {
                    line.align = Some(part[1..part.len() - 1].into());
                    continue;
                }
                "[b]" => {
                    bold.push(true);
                    continue;
                }
                "[regular]" => {
                    bold.push(false);
                    continue;
                }
                "[/b]" | "[/regular]" => {
                    if bold.len() > 1 {
                        bold.pop();
                    }
                    continue;
                }
                "[/size]" => {
                    if sizes.len() > 1 {
                        sizes.pop();
                    }
                    continue;
                }
                _ => {}
            }
            if part.starts_with("[size:") {
                let v: f64 = part[6..part.len() - 1]
                    .parse()
                    .map_err(|_| "Invalid text size")?;
                if !(8. ..=240.).contains(&v) {
                    return Err("Text size must be 8–240 px".into());
                }
                sizes.push(v);
                continue;
            }
            let atoms = if part.starts_with("[icon:") {
                let p = part[1..part.len() - 1].split(':').collect::<Vec<_>>();
                vec![self.icon(
                    p[1],
                    if p.len() == 3 {
                        p[2].parse().map_err(|_| "Invalid icon size")?
                    } else {
                        self.icon
                    },
                )?]
            } else {
                words
                    .find_iter(part)
                    .map(|m| self.text(m.as_str(), *sizes.last().unwrap(), *bold.last().unwrap()))
                    .collect()
            };
            for atom in atoms {
                if let Some(max) = max {
                    if atom.w > max {
                        return Err("A word or icon is wider than the label. Reduce its size or side inset.".into());
                    }
                    if !line.atoms.is_empty() && line.w() + atom.w > max {
                        finish(&mut lines, &mut line);
                    }
                }
                if line.atoms.is_empty() && atom.space {
                    continue;
                }
                line.atoms.push(atom);
            }
        }
        finish(&mut lines, &mut line);
        let w = lines.iter().map(Line::w).fold(0., f64::max);
        let h = lines.iter().map(|l| l.h(self.size)).sum::<f64>()
            + self.gap * (lines.len().saturating_sub(1)) as f64;
        Ok(Block {
            lines,
            w,
            h,
            base: self.size,
            gap: self.gap,
        })
    }
}
fn border(x: f64, y: f64, w: f64, h: f64, r: f64, stroke: f64) -> String {
    if stroke <= 0. {
        return String::new();
    }
    let inset = stroke / 2.;
    format!("<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" rx=\"{}\" fill=\"none\" stroke=\"black\" stroke-width=\"{stroke}\"/>",x+inset,y+inset,(w-stroke).max(0.),(h-stroke).max(0.),r.min(w/2.).min(h/2.))
}
fn svg_image(body: &str, height: u32) -> R<GrayImage> {
    if height == 0 || height > 12000 {
        return Err("Batch exceeds the one-metre limit.".into());
    }
    let svg=format!("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"576\" height=\"{height}\"><rect width=\"576\" height=\"{height}\" fill=\"white\"/><g fill=\"black\">{body}</g></svg>");
    let tree =
        resvg::usvg::Tree::from_str(&svg, &resources().options).map_err(|e| e.to_string())?;
    let mut pixmap =
        resvg::tiny_skia::Pixmap::new(576, height).ok_or("Could not allocate image")?;
    resvg::render(
        &tree,
        resvg::tiny_skia::Transform::identity(),
        &mut pixmap.as_mut(),
    );
    Ok(GrayImage::from_fn(576, height, |x, y| {
        let p = pixmap.pixel(x, y).unwrap();
        Luma([if p.red() < 128 { 0 } else { 255 }])
    }))
}
fn machine(text: &str, s: &Value) -> R<(GrayImage, Value)> {
    if text.trim().is_empty() {
        return Err("Enter label text first.".into());
    }
    let rich = Rich::new(s)?;
    let length = n(s, "label_length_mm", 30., 5., 500.)?;
    let stroke = n(s, "stroke", 2., 0., 16.)?;
    let radius = n(s, "radius_mm", 1.5, 0., 20.)? / DOT_MM;
    let boxed = b(s, "border", true);
    let pad = (n(s, "padding_mm", 2.5, 0., 20.)? * 576. / 44.)
        .round()
        .max(if boxed { 8. + stroke } else { 0. });
    let block = rich.layout(text, Some(576. - 2. * pad))?;
    let vertical = if boxed { (stroke + 8.).max(10.) } else { 4. };
    let height = if st(s, "layout", "label") == "note" {
        (block.h + 2. * vertical).ceil() as u32
    } else {
        (length / DOT_MM).round() as u32
    };
    if block.h + 2. * vertical > height as f64 {
        return Err("Text or icons do not fit vertically. Increase label length or reduce size/line spacing.".into());
    }
    let align = alignment(st(s, "align", "center"))?;
    let mut svg = block.paint(pad, (height as f64 - block.h) / 2., 576. - 2. * pad, align);
    if boxed {
        svg += &border(8., 8., 560., height as f64 - 16., radius, stroke);
    }
    Ok((svg_image(&svg, height)?, json!({})))
}
fn cables(text: &str, s: &Value) -> R<(GrayImage, Value)> {
    let values: Value = serde_json::from_str(text).map_err(|e| e.to_string())?;
    let cols = n(s, "columns", 2., 2., 4.)? as usize;
    if cols != 2 && cols != 4 {
        return Err("Choose 2 or 4 columns.".into());
    }
    let split = |key| {
        st(&values, key, "")
            .lines()
            .map(|t| t.trim().to_string())
            .collect::<Vec<_>>()
    };
    let left = split("left");
    let extra = if cols == 4 {
        split("left_extra")
    } else {
        vec![]
    };
    let right = if b(s, "mirror", true) {
        left.clone()
    } else {
        split("right")
    };
    let right_extra = if cols != 4 {
        vec![]
    } else if b(s, "mirror", true) {
        extra.clone()
    } else {
        split("right_extra")
    };
    let mut fields = [left, extra, right, right_extra];
    let source = fields.iter().map(Vec::len).max().unwrap_or(0);
    if source == 0 || source > 50 {
        return Err("Enter 1–50 label rows.".into());
    }
    if fields.iter().flatten().all(|v| v.is_empty()) {
        return Err("Enter at least one cable name.".into());
    }
    for field in &mut fields {
        field.resize(source, String::new());
    }
    let empty = vec![];
    let copies_input = match values.get("copies") {
        Some(v) => v.as_array().ok_or("Invalid copy counts")?,
        None => &empty,
    };
    if copies_input.len() > source {
        return Err("Too many copy counts.".into());
    }
    let mut copies = vec![];
    for i in 0..source {
        let qty = match copies_input.get(i) {
            None => 1,
            Some(v) => v.as_u64().ok_or("Copies must be whole numbers")?,
        };
        if !(1..=50).contains(&qty) {
            return Err(format!("Row {}: copies must be 1–50.", i + 1));
        }
        copies.push(qty as usize);
    }
    let count: usize = copies.iter().sum();
    if count > 50 {
        return Err(format!(
            "Batch has {count} labels; maximum is 50 including copies."
        ));
    }
    let order = copies
        .iter()
        .enumerate()
        .flat_map(|(i, n)| std::iter::repeat_n(i, *n))
        .collect::<Vec<_>>();
    let width = (n(s, "width_mm", 44., 5., 44.)? * 576. / 44.).round();
    let row = (n(s, "row_mm", 10., 5., 100.)? / DOT_MM).round();
    let gap = (n(s, "gap_mm", 2., 0., 30.)? / DOT_MM).round();
    let fold = (n(s, "fold_mm", 4., 0., 30.)? * 576. / 44.).round();
    let stroke = n(s, "stroke", 2., 0., 16.)?;
    let radius = (n(s, "radius_mm", 1.5, 0., 20.)? / DOT_MM).round();
    let pad = stroke + (n(s, "padding_mm", 2.5, 0., 20.)? * 576. / 44.).round();
    let half = (width / 2.).floor() - (fold / 2.).floor() - 2. * pad;
    let field_gap = (n(s, "field_gap_mm", 1., 0., 20.)? * 576. / 44.).round();
    let fraction = n(s, "first_field_percent", 40., 5., 95.)? / 100.;
    if half <= 0. || (cols == 4 && half <= field_gap) {
        return Err("No room for text. Reduce inset, fold or field gaps.".into());
    }
    let height = (count as f64 * row + (count - 1) as f64 * gap) as u32;
    if height > 12000 {
        return Err("Batch is too long; split into smaller batches.".into());
    }
    let rich = Rich::new(s)?;
    let mut blocks: Vec<Vec<Block>> = vec![];
    for field in &fields {
        blocks.push(
            field
                .iter()
                .map(|t| rich.layout(t, None))
                .collect::<R<Vec<_>>>()?,
        );
    }
    let mut first = [half; 2];
    if cols == 4 {
        for side in 0..2 {
            let need1 = blocks[side * 2].iter().map(|p| p.w).fold(0., f64::max);
            let need2 = blocks[side * 2 + 1].iter().map(|p| p.w).fold(0., f64::max);
            let usable = half - field_gap;
            let mut preferred = (usable * fraction).round();
            if b(s, "auto_field_widths", true) {
                if need1 + need2 > usable {
                    return Err(format!("{} side needs {:.1} mm for both fields; only {:.1} mm is available. Reduce text/icon size, inset or fold space.",if side==0{"Left"}else{"Right"},(need1+need2+field_gap)*44./576.,half*44./576.));
                }
                preferred = preferred.max(need1).min(usable - need2);
            }
            first[side] = preferred;
        }
    }
    let x0 = ((576. - width) / 2.).floor();
    let x1 = ((576. + width) / 2.).floor() - 1.;
    let mut svg = String::new();
    let mut guide_rows = vec![];
    let mut guide_fields = vec![];
    let border_mode = st(s, "border_mode", "Whole row");
    if !["Whole row", "Each half"].contains(&border_mode) {
        return Err("Invalid border mode".into());
    }
    for (i, &source_row) in order.iter().enumerate() {
        let top = i as f64 * (row + gap);
        guide_rows.push(json!([x0, top, width, row]));
        if border_mode == "Whole row" {
            svg += &border(x0, top, width, row, radius, stroke);
        } else {
            svg += &border(
                x0,
                top,
                288. - (fold / 2.).floor() - x0,
                row,
                radius,
                stroke,
            );
            let x = 288. + (fold / 2.).floor();
            svg += &border(x, top, x1 - x + 1., row, radius, stroke);
        }
        for side in 0..2 {
            let name = if side == 0 { "left" } else { "right" };
            let mut positions = if cols == 2 {
                vec![(side * 2, half)]
            } else {
                vec![
                    (side * 2, first[side]),
                    (side * 2 + 1, half - field_gap - first[side]),
                ]
            };
            if cols == 4 && b(s, &format!("{name}_swap"), false) {
                positions.reverse();
            }
            let mut x = if side == 0 { x0 + pad } else { x1 - pad - half };
            for (field, area) in positions {
                let block = &blocks[field][source_row];
                let key = format!("{name}{}_align", if field % 2 == 1 { "_extra" } else { "" });
                let align = alignment(st(s, &key, if side == 0 { "left" } else { "right" }))?;
                guide_fields.push(json!([
                    x,
                    top + stroke + 4.,
                    area,
                    row - 2. * (stroke + 4.)
                ]));
                if !fields[field][source_row].is_empty() {
                    if block.w > area + 0.01 || block.h > row - 2. * (stroke + 4.) {
                        return Err(format!("Row {}, {name} field {} does not fit. Reduce size, increase row/label dimensions or enable shared field widths.",source_row+1,field%2+1));
                    }
                    svg += &block.paint(x, top + (row - block.h) / 2., area, align);
                }
                x += area + field_gap;
            }
        }
        if b(s, "fold_mark", false) {
            svg+=&format!("<path d=\"M288 {} V{}\" stroke=\"black\" stroke-width=\"1\" stroke-dasharray=\"5 7\"/>",top+8.,top+row-8.);
        }
    }
    Ok((
        svg_image(&svg, height)?,
        json!({"rows":count,"source_rows":source,"copies":copies,"columns":cols,"guides":{"fields":guide_fields,"rows":guide_rows,"fold":[288.-(fold/2.).floor(),fold],"content_height":height}}),
    ))
}
fn picture(data: &Value) -> R<GrayImage> {
    let bytes = B64
        .decode(st(data, "image", ""))
        .map_err(|_| "Invalid image data")?;
    if bytes.len() > 20 * 1024 * 1024 {
        return Err("Choose an image smaller than 20 MB.".into());
    }
    let mut reader = image::ImageReader::new(Cursor::new(bytes))
        .with_guessed_format()
        .map_err(|e| e.to_string())?;
    let mut limits = image::Limits::default();
    limits.max_image_width = Some(8192);
    limits.max_image_height = Some(8192);
    limits.max_alloc = Some(128 * 1024 * 1024);
    reader.limits(limits);
    let rgba = reader.decode().map_err(|e| e.to_string())?.to_rgba8();
    let (w, h) = rgba.dimensions();
    if w == 0 || h == 0 {
        return Err("Empty image".into());
    }
    let mut gray = GrayImage::from_fn(w, h, |x, y| {
        let p = rgba.get_pixel(x, y);
        let a = p[3] as f64 / 255.;
        let luminance = 0.299 * p[0] as f64 + 0.587 * p[1] as f64 + 0.114 * p[2] as f64;
        Luma([(luminance * a + 255. * (1. - a)).round() as u8])
    });
    let scale = (576. / w as f64).min((200. / DOT_MM) / h as f64);
    let nw = (w as f64 * scale).round().max(1.) as u32;
    let nh = (h as f64 * scale).round().max(1.) as u32;
    gray = image::imageops::resize(&gray, nw, nh, image::imageops::FilterType::Lanczos3);
    match st(data, "mode", "sticker") {
        "photo" => image::imageops::dither(&mut gray, &image::imageops::BiLevel),
        "sticker" => {
            for p in gray.pixels_mut() {
                p[0] = if p[0] < 128 { 0 } else { 255 };
            }
        }
        _ => return Err("Invalid image conversion".into()),
    }
    let mut canvas = GrayImage::from_pixel(576, nh, Luma([255]));
    image::imageops::overlay(&mut canvas, &gray, ((576 - nw) / 2) as i64, 0);
    Ok(canvas)
}
pub struct Rendered {
    pub meta: Value,
    pub raster: Vec<u8>,
}
pub fn render(data: &Value) -> R<Rendered> {
    let s = &data["settings"];
    let kind = st(data, "kind", "");
    let text = st(data, "content", "");
    if text.len() > 40000 {
        return Err("Text is too long.".into());
    }
    let (content, mut meta) = match kind {
        "paragraph" => machine(text, s)?,
        "cable" => cables(text, s)?,
        "image" => (picture(data)?, json!({})),
        _ => return Err("Invalid print mode".into()),
    };
    let lead = n(s, "leading_mm", 0., 0., 100.)?;
    let tail = n(s, "trailing_mm", 14., 0., 100.)?;
    let lr = (lead / DOT_MM).round() as u32;
    let tr = (tail / DOT_MM).round() as u32;
    let height = content.height() + lr + tr;
    if height > 12000 || height == 0 {
        return Err("Total print length exceeds the one-metre limit.".into());
    }
    let mut preview = GrayImage::from_pixel(576, height, Luma([255]));
    image::imageops::overlay(&mut preview, &content, 0, lr as i64);
    let mut raster = vec![0u8; (height * 72) as usize];
    for (x, y, p) in preview.enumerate_pixels() {
        if p[0] < 128 {
            raster[(y * 72 + x / 8) as usize] |= 1 << (7 - x % 8);
        }
    }
    let mut png = Cursor::new(Vec::new());
    DynamicImage::ImageLuma8(preview)
        .write_to(&mut png, ImageFormat::Png)
        .map_err(|e| e.to_string())?;
    let fields = json!({"width":576,"height":height,"content_height":content.height(),"leading_rows":lr,"trailing_rows":tr,"leading_mm":lead,"trailing_mm":tail,"estimated_length_mm":(height as f64*DOT_MM*10.).round()/10.,"preview_png":B64.encode(png.into_inner()),"renderer":"Rust/native","bytes_prepared":raster.len()});
    meta.as_object_mut()
        .unwrap()
        .extend(fields.as_object().unwrap().clone());
    Ok(Rendered { meta, raster })
}
