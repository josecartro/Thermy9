use base64::{engine::general_purpose::STANDARD as B64, Engine};
use serde_json::{json, Value};
use thermy9::render::render;
fn cable(s: Value, content: Value) -> Value {
    json!({"kind":"cable","settings":s,"content":content.to_string()})
}
#[test]
fn five_mm_machine_and_exact_preview() {
    let r=render(&json!({"kind":"paragraph","content":"PORT 3","settings":{"font_size":16,"label_length_mm":5,"trailing_mm":0}})).unwrap();
    assert_eq!(r.meta["height"], 59);
    let png = B64.decode(r.meta["preview_png"].as_str().unwrap()).unwrap();
    let pixels = image::load_from_memory(&png).unwrap().to_luma8();
    for (x, y, p) in pixels.enumerate_pixels() {
        assert_eq!(
            p[0] == 0,
            (r.raster[(y * 72 + x / 8) as usize] & (1 << (7 - x % 8))) != 0
        );
    }
}
#[test]
fn rich_lines_icons_and_copies() {
    let r=render(&cable(json!({"columns":2,"font_size":16,"bold":false,"row_mm":12}),json!({"left":"[icon:network:24] [b]GB10[/b][br][regular][size:12]Port-3[/size][/regular]","copies":[4]}))).unwrap();
    assert_eq!(r.meta["rows"], 4);
    assert_eq!(r.meta["source_rows"], 1);
    let row = (12f64 / 0.08472).round() as usize;
    let gap = (2f64 / 0.08472).round() as usize;
    for i in 1..4 {
        assert_eq!(
            &r.raster[..row * 72],
            &r.raster[i * (row + gap) * 72..(i * (row + gap) + row) * 72]
        );
    }
}
#[test]
fn screenshot_name_and_port_fit() {
    render(&cable(json!({"columns":4,"font_size":16,"bold":false,"width_mm":42,"padding_mm":2.5,"fold_mm":4,"right_swap":true}),json!({"left":"GB10-BM-03","left_extra":"Port-3"}))).unwrap();
}
#[test]
fn all_icons_render() {
    let icons: Value = serde_json::from_str(include_str!("../../web/icons.json")).unwrap();
    for name in icons.as_object().unwrap().keys() {
        let r=render(&json!({"kind":"paragraph","content":format!("[icon:{name}:48]"),"settings":{"label_length_mm":10,"font_size":16,"border":false,"trailing_mm":0}})).unwrap();
        assert!(r.raster.iter().any(|b| *b != 0), "{name}");
    }
}
#[test]
fn invalid_counts_overflow_and_icons_fail() {
    for count in [json!(0), json!(1.5), json!(true), json!(51)] {
        assert!(render(&cable(json!({}), json!({"left":"A","copies":[count]}))).is_err());
    }
    assert!(render(&cable(
        json!({"columns":4,"font_size":100}),
        json!({"left":"GB10-BM-03","left_extra":"192.0.2.10"})
    ))
    .is_err());
    assert!(render(&json!({"kind":"paragraph","content":"[icon:missing]"})).is_err());
}
#[test]
fn swap_and_align_change_pixels_not_copies() {
    let mut request = cable(
        json!({"columns":4,"font_size":16,"mirror":false}),
        json!({"left":"AA","left_extra":"BB","right":"CC","right_extra":"DD"}),
    );
    let plain = render(&request).unwrap();
    request["settings"]["right_swap"] = json!(true);
    let swapped = render(&request).unwrap();
    assert_ne!(plain.raster, swapped.raster);
    request["settings"]["left_align"] = json!("center");
    assert_ne!(swapped.raster, render(&request).unwrap().raster);
    assert_eq!(swapped.meta["rows"], 1);
}
#[test]
fn feed_is_blank_and_once_per_batch() {
    let r = render(&cable(
        json!({"leading_mm":3,"trailing_mm":20,"font_size":16}),
        json!({"left":"A\nB","copies":[2,3]}),
    ))
    .unwrap();
    let lead = r.meta["leading_rows"].as_u64().unwrap() as usize * 72;
    let tail = r.meta["trailing_rows"].as_u64().unwrap() as usize * 72;
    assert!(r.raster[..lead].iter().all(|v| *v == 0));
    assert!(r.raster[r.raster.len() - tail..].iter().all(|v| *v == 0));
    assert_eq!(r.meta["rows"], 5);
}
#[test]
fn image_modes_and_transparency() {
    let image = image::RgbaImage::from_fn(16, 16, |x, y| {
        image::Rgba([128, 128, 128, if x < 8 && y < 8 { 0 } else { 255 }])
    });
    let mut png = std::io::Cursor::new(Vec::new());
    image::DynamicImage::ImageRgba8(image)
        .write_to(&mut png, image::ImageFormat::Png)
        .unwrap();
    let data = B64.encode(png.into_inner());
    let sticker = render(&json!({"kind":"image","image":data,"mode":"sticker"})).unwrap();
    let photo = render(&json!({"kind":"image","image":data,"mode":"photo"})).unwrap();
    assert_ne!(sticker.raster, photo.raster);
    assert_eq!(photo.meta["width"], 576);
    assert!(photo.raster[..72].iter().take(30).all(|v| *v == 0));
}
