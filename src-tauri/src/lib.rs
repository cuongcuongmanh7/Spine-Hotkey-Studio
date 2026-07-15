use chrono::{Local, SecondsFormat};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, HashMap};
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::Command;
use tauri::{AppHandle, Manager};

const PRESET_FORMAT_VERSION: u8 = 1;

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct HotkeyEntry {
    entry_id: String,
    section: String,
    section_occurrence: usize,
    group_label: String,
    action: String,
    action_occurrence: usize,
    value: String,
    original_value: String,
    line_index: usize,
}

#[derive(Debug)]
struct HotkeyDocument {
    lines: Vec<String>,
    newline: String,
    trailing_newline: bool,
    entries: Vec<HotkeyEntry>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct HotkeySnapshot {
    path: String,
    source_token: String,
    structure_fingerprint: String,
    entries: Vec<HotkeyEntry>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct SaveHotkeysRequest {
    source_token: String,
    bindings: BTreeMap<String, String>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct SaveHotkeysResult {
    source_token: String,
    backup_path: String,
    updated_count: usize,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct PresetPayload {
    #[serde(alias = "format_version")]
    format_version: u8,
    name: String,
    #[serde(alias = "created_at")]
    created_at: String,
    #[serde(alias = "source_file")]
    source_file: String,
    #[serde(alias = "structure_fingerprint")]
    structure_fingerprint: String,
    bindings: BTreeMap<String, String>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct SavePresetRequest {
    name: String,
    source_file: String,
    structure_fingerprint: String,
    bindings: BTreeMap<String, String>,
    overwrite: bool,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct PresetSummary {
    file_name: String,
    name: String,
    created_at: String,
    binding_count: usize,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct RenamePresetRequest {
    file_name: String,
    new_name: String,
}

#[tauri::command]
fn load_hotkeys(app: AppHandle) -> Result<HotkeySnapshot, String> {
    let path = hotkey_path(&app)?;
    let bytes = fs::read(&path)
        .map_err(|error| format!("Không thể đọc {}: {error}", path.to_string_lossy()))?;
    let document = HotkeyDocument::parse(&bytes)?;
    Ok(HotkeySnapshot {
        path: path.to_string_lossy().into_owned(),
        source_token: hash_bytes(&bytes),
        structure_fingerprint: document.structure_fingerprint(),
        entries: document.entries,
    })
}

#[tauri::command]
fn save_hotkeys(app: AppHandle, request: SaveHotkeysRequest) -> Result<SaveHotkeysResult, String> {
    if is_spine_running() {
        return Err("SPINE_RUNNING:Hãy đóng Spine hoàn toàn trước khi áp dụng hotkey.".into());
    }

    let path = hotkey_path(&app)?;
    let bytes = fs::read(&path).map_err(|error| format!("Không thể đọc hotkeys.txt: {error}"))?;
    if hash_bytes(&bytes) != request.source_token {
        return Err(
            "FILE_CHANGED:hotkeys.txt đã được chương trình khác thay đổi. Hãy tải lại trước khi áp dụng."
                .into(),
        );
    }

    let mut document = HotkeyDocument::parse(&bytes)?;
    let mut updated_count = 0;
    for entry in &mut document.entries {
        if let Some(value) = request.bindings.get(&entry.entry_id) {
            let cleaned = clean_hotkey(value);
            if entry.value != cleaned {
                updated_count += 1;
                entry.value = cleaned;
            }
        }
    }

    let backup_dir = data_dir(&app)?.join("backups");
    fs::create_dir_all(&backup_dir)
        .map_err(|error| format!("Không thể tạo thư mục backup: {error}"))?;
    let stamp = Local::now().format("%Y%m%d-%H%M%S-%3f");
    let backup_path = backup_dir.join(format!("hotkeys-{stamp}.txt.bak"));
    fs::copy(&path, &backup_path).map_err(|error| format!("Không thể tạo backup: {error}"))?;

    let output = document.render().into_bytes();
    write_atomic(&path, &output)?;
    Ok(SaveHotkeysResult {
        source_token: hash_bytes(&output),
        backup_path: backup_path.to_string_lossy().into_owned(),
        updated_count,
    })
}

#[tauri::command]
fn list_presets(app: AppHandle) -> Result<Vec<PresetSummary>, String> {
    let directory = preset_dir(&app)?;
    fs::create_dir_all(&directory)
        .map_err(|error| format!("Không thể tạo thư mục preset: {error}"))?;
    let mut presets = Vec::new();
    for item in
        fs::read_dir(&directory).map_err(|error| format!("Không thể đọc preset: {error}"))?
    {
        let path = match item {
            Ok(entry) => entry.path(),
            Err(_) => continue,
        };
        if path.extension().and_then(|value| value.to_str()) != Some("json") {
            continue;
        }
        let payload = match read_preset(&path) {
            Ok(value) => value,
            Err(_) => continue,
        };
        presets.push(PresetSummary {
            file_name: path
                .file_name()
                .and_then(|value| value.to_str())
                .unwrap_or_default()
                .to_string(),
            name: payload.name,
            created_at: payload.created_at,
            binding_count: payload.bindings.len(),
        });
    }
    presets.sort_by(|left, right| right.created_at.cmp(&left.created_at));
    Ok(presets)
}

#[tauri::command]
fn load_preset(app: AppHandle, file_name: String) -> Result<PresetPayload, String> {
    let path = checked_preset_path(&app, &file_name)?;
    read_preset(&path)
}

#[tauri::command]
fn save_preset(app: AppHandle, request: SavePresetRequest) -> Result<PresetSummary, String> {
    let name = request.name.trim();
    if name.is_empty() {
        return Err("Tên preset không được để trống.".into());
    }
    let directory = preset_dir(&app)?;
    fs::create_dir_all(&directory)
        .map_err(|error| format!("Không thể tạo thư mục preset: {error}"))?;
    let file_name = safe_preset_file_name(name);
    let path = directory.join(&file_name);
    if path.exists() && !request.overwrite {
        return Err("PRESET_EXISTS:Preset này đã tồn tại.".into());
    }
    let payload = PresetPayload {
        format_version: PRESET_FORMAT_VERSION,
        name: name.to_string(),
        created_at: Local::now().to_rfc3339_opts(SecondsFormat::Secs, true),
        source_file: request.source_file,
        structure_fingerprint: request.structure_fingerprint,
        bindings: request.bindings,
    };
    write_json(&path, &payload)?;
    Ok(PresetSummary {
        file_name,
        name: payload.name,
        created_at: payload.created_at,
        binding_count: payload.bindings.len(),
    })
}

#[tauri::command]
fn rename_preset(app: AppHandle, request: RenamePresetRequest) -> Result<PresetSummary, String> {
    let old_path = checked_preset_path(&app, &request.file_name)?;
    let mut payload = read_preset(&old_path)?;
    let new_name = request.new_name.trim();
    if new_name.is_empty() {
        return Err("Tên preset không được để trống.".into());
    }
    let new_file_name = safe_preset_file_name(new_name);
    let new_path = preset_dir(&app)?.join(&new_file_name);
    if new_path.exists() && new_path != old_path {
        return Err("PRESET_EXISTS:Preset này đã tồn tại.".into());
    }
    payload.name = new_name.to_string();
    write_json(&new_path, &payload)?;
    if new_path != old_path {
        fs::remove_file(&old_path)
            .map_err(|error| format!("Không thể xóa tên preset cũ: {error}"))?;
    }
    Ok(PresetSummary {
        file_name: new_file_name,
        name: payload.name,
        created_at: payload.created_at,
        binding_count: payload.bindings.len(),
    })
}

#[tauri::command]
fn duplicate_preset(app: AppHandle, request: RenamePresetRequest) -> Result<PresetSummary, String> {
    let source_path = checked_preset_path(&app, &request.file_name)?;
    let mut payload = read_preset(&source_path)?;
    let new_name = request.new_name.trim();
    if new_name.is_empty() {
        return Err("Tên preset không được để trống.".into());
    }
    let file_name = safe_preset_file_name(new_name);
    let path = preset_dir(&app)?.join(&file_name);
    if path.exists() {
        return Err("PRESET_EXISTS:Preset này đã tồn tại.".into());
    }
    payload.name = new_name.to_string();
    payload.created_at = Local::now().to_rfc3339_opts(SecondsFormat::Secs, true);
    write_json(&path, &payload)?;
    Ok(PresetSummary {
        file_name,
        name: payload.name,
        created_at: payload.created_at,
        binding_count: payload.bindings.len(),
    })
}

#[tauri::command]
fn delete_preset(app: AppHandle, file_name: String) -> Result<(), String> {
    let path = checked_preset_path(&app, &file_name)?;
    fs::remove_file(path).map_err(|error| format!("Không thể xóa preset: {error}"))
}

fn hotkey_path(app: &AppHandle) -> Result<PathBuf, String> {
    app.path()
        .home_dir()
        .map(|path| path.join("Spine").join("hotkeys.txt"))
        .map_err(|error| format!("Không xác định được thư mục người dùng: {error}"))
}

fn data_dir(app: &AppHandle) -> Result<PathBuf, String> {
    app.path()
        .app_data_dir()
        .map_err(|error| format!("Không xác định được thư mục dữ liệu ứng dụng: {error}"))
}

fn preset_dir(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(data_dir(app)?.join("presets"))
}

fn checked_preset_path(app: &AppHandle, file_name: &str) -> Result<PathBuf, String> {
    let candidate = Path::new(file_name);
    if candidate.file_name().and_then(|value| value.to_str()) != Some(file_name)
        || candidate.extension().and_then(|value| value.to_str()) != Some("json")
    {
        return Err("Tên file preset không hợp lệ.".into());
    }
    let path = preset_dir(app)?.join(candidate);
    if !path.exists() {
        return Err("Không tìm thấy preset.".into());
    }
    Ok(path)
}

fn read_preset(path: &Path) -> Result<PresetPayload, String> {
    let content =
        fs::read_to_string(path).map_err(|error| format!("Không thể đọc preset: {error}"))?;
    let payload: PresetPayload =
        serde_json::from_str(&content).map_err(|error| format!("Preset không hợp lệ: {error}"))?;
    if payload.format_version != PRESET_FORMAT_VERSION {
        return Err("Phiên bản preset chưa được hỗ trợ.".into());
    }
    Ok(payload)
}

fn write_json(path: &Path, payload: &PresetPayload) -> Result<(), String> {
    let mut content = serde_json::to_string_pretty(payload)
        .map_err(|error| format!("Không thể mã hóa preset: {error}"))?;
    content.push('\n');
    fs::write(path, content).map_err(|error| format!("Không thể lưu preset: {error}"))
}

fn safe_preset_file_name(name: &str) -> String {
    let mut output = String::new();
    let mut previous_dash = false;
    for character in name.trim().chars() {
        let normalized = if character.is_alphanumeric() || matches!(character, '-' | '_' | '.') {
            Some(character)
        } else if character.is_whitespace() {
            Some('-')
        } else {
            None
        };
        if let Some(character) = normalized {
            if character == '-' {
                if previous_dash {
                    continue;
                }
                previous_dash = true;
            } else {
                previous_dash = false;
            }
            output.push(character);
        }
        if output.chars().count() >= 80 {
            break;
        }
    }
    let cleaned = output.trim_matches(['.', '-', '_']).to_string();
    format!(
        "{}.json",
        if cleaned.is_empty() {
            "preset"
        } else {
            &cleaned
        }
    )
}

fn hash_bytes(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn clean_hotkey(value: &str) -> String {
    value
        .trim()
        .split('+')
        .map(str::trim)
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join(" + ")
}

impl HotkeyDocument {
    fn parse(bytes: &[u8]) -> Result<Self, String> {
        let decoded = std::str::from_utf8(bytes)
            .map_err(|_| "hotkeys.txt không dùng encoding UTF-8 hợp lệ.".to_string())?;
        let text = decoded.strip_prefix('\u{feff}').unwrap_or(decoded);
        let newline = if text.contains("\r\n") { "\r\n" } else { "\n" }.to_string();
        let trailing_newline = text.ends_with('\n');
        let lines: Vec<String> = text
            .lines()
            .map(|line| line.trim_end_matches('\r').to_string())
            .collect();

        let mut entries = Vec::new();
        let mut section = "Khác".to_string();
        let mut section_occurrence = 0usize;
        let mut section_counts: HashMap<String, usize> = HashMap::new();
        let mut action_counts: HashMap<(String, usize, String), usize> = HashMap::new();

        for (line_index, line) in lines.iter().enumerate() {
            if let Some(section_name) = parse_section(line) {
                section = section_name;
                let count = section_counts.entry(section.clone()).or_default();
                *count += 1;
                section_occurrence = *count;
                continue;
            }
            let Some((action_part, value_part)) = line.split_once(':') else {
                continue;
            };
            let action = action_part.trim();
            if action.is_empty() || line.starts_with("---") {
                continue;
            }
            let key = (section.clone(), section_occurrence, action.to_string());
            let count = action_counts.entry(key).or_default();
            *count += 1;
            let action_occurrence = *count;
            let value = value_part.trim().to_string();
            let group_label = if section_occurrence > 1 {
                format!("{} ({section_occurrence})", section)
            } else {
                section.clone()
            };
            entries.push(HotkeyEntry {
                entry_id: make_entry_id(&section, section_occurrence, action, action_occurrence),
                section: section.clone(),
                section_occurrence,
                group_label,
                action: action.to_string(),
                action_occurrence,
                original_value: value.clone(),
                value,
                line_index,
            });
        }
        if entries.is_empty() {
            return Err("Không tìm thấy dòng hotkey hợp lệ trong file.".into());
        }
        Ok(Self {
            lines,
            newline,
            trailing_newline,
            entries,
        })
    }

    fn render(&self) -> String {
        let mut lines = self.lines.clone();
        for entry in &self.entries {
            if let Some((prefix, _)) = lines[entry.line_index].split_once(':') {
                lines[entry.line_index] = format!("{}: {}", prefix.trim_end(), entry.value);
            }
        }
        let mut output = lines.join(&self.newline);
        if self.trailing_newline {
            output.push_str(&self.newline);
        }
        output
    }

    fn structure_fingerprint(&self) -> String {
        let joined = self
            .entries
            .iter()
            .map(|entry| entry.entry_id.as_str())
            .collect::<Vec<_>>()
            .join("\n");
        hash_bytes(joined.as_bytes())[..16].to_string()
    }
}

fn parse_section(line: &str) -> Option<String> {
    let trimmed = line.trim();
    if trimmed.starts_with("--- ") && trimmed.ends_with(" ---") && trimmed.len() > 8 {
        Some(trimmed[4..trimmed.len() - 4].trim().to_string())
    } else {
        None
    }
}

fn make_entry_id(
    section: &str,
    section_occurrence: usize,
    action: &str,
    action_occurrence: usize,
) -> String {
    format!("{section}\u{1f}{section_occurrence}\u{1f}{action}\u{1f}{action_occurrence}")
}

fn is_spine_running() -> bool {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        let output = Command::new("tasklist")
            .args(["/FO", "CSV", "/NH"])
            .creation_flags(CREATE_NO_WINDOW)
            .output();
        let Ok(output) = output else {
            return false;
        };
        String::from_utf8_lossy(&output.stdout).lines().any(|line| {
            let process = line
                .trim_start_matches('\u{feff}')
                .trim()
                .trim_start_matches('"')
                .split('"')
                .next()
                .unwrap_or_default()
                .to_ascii_lowercase();
            is_spine_process_name(&process)
        })
    }
    #[cfg(not(windows))]
    {
        false
    }
}

fn is_spine_process_name(process: &str) -> bool {
    let normalized = process.trim().to_ascii_lowercase();
    if normalized == "spine.exe" {
        return true;
    }
    normalized
        .strip_prefix("spine-")
        .and_then(|name| name.strip_suffix(".exe"))
        .and_then(|version| version.chars().next())
        .is_some_and(|character| character.is_ascii_digit())
}

fn write_atomic(path: &Path, bytes: &[u8]) -> Result<(), String> {
    let parent = path
        .parent()
        .ok_or_else(|| "Đường dẫn hotkeys.txt không hợp lệ.".to_string())?;
    let temp_path = parent.join(format!(
        ".{}.{}.tmp",
        path.file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("hotkeys"),
        std::process::id()
    ));
    let mut file = OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(&temp_path)
        .map_err(|error| format!("Không thể tạo file tạm: {error}"))?;
    let result = (|| -> Result<(), String> {
        file.write_all(bytes)
            .map_err(|error| format!("Không thể ghi file tạm: {error}"))?;
        file.sync_all()
            .map_err(|error| format!("Không thể đồng bộ file tạm: {error}"))?;
        drop(file);
        replace_file(path, &temp_path)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp_path);
    }
    result
}

#[cfg(windows)]
fn replace_file(target: &Path, replacement: &Path) -> Result<(), String> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::ReplaceFileW;
    let target_wide: Vec<u16> = target.as_os_str().encode_wide().chain(Some(0)).collect();
    let replacement_wide: Vec<u16> = replacement
        .as_os_str()
        .encode_wide()
        .chain(Some(0))
        .collect();
    let result = unsafe {
        ReplaceFileW(
            target_wide.as_ptr(),
            replacement_wide.as_ptr(),
            std::ptr::null(),
            0,
            std::ptr::null_mut(),
            std::ptr::null_mut(),
        )
    };
    if result == 0 {
        Err(format!(
            "Không thể thay file hotkey an toàn: {}",
            std::io::Error::last_os_error()
        ))
    } else {
        Ok(())
    }
}

#[cfg(not(windows))]
fn replace_file(target: &Path, replacement: &Path) -> Result<(), String> {
    fs::rename(replacement, target).map_err(|error| format!("Không thể thay file hotkey: {error}"))
}

pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            load_hotkeys,
            save_hotkeys,
            list_presets,
            load_preset,
            save_preset,
            rename_preset,
            duplicate_preset,
            delete_preset
        ])
        .run(tauri::generate_context!())
        .expect("error while running Spine Hotkey Studio");
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = "--- General ---\r\nUndo: ctrl + Z\r\nRedo: ctrl + Y\r\nRedo: ctrl + shift + Z\r\n--- General ---\r\nNext Skin: PERIOD\r\n--- Playback ---\r\nNext Key: 'W'\r\nPrevious Key: \r\n";

    #[test]
    fn round_trip_preserves_crlf_and_duplicates() {
        let document = HotkeyDocument::parse(SAMPLE.as_bytes()).unwrap();
        assert_eq!(document.render(), SAMPLE);
        assert_eq!(document.entries.len(), 6);
        assert_ne!(document.entries[1].entry_id, document.entries[2].entry_id);
        assert_eq!(document.entries[3].group_label, "General (2)");
    }

    #[test]
    fn editing_one_entry_preserves_the_rest() {
        let mut document = HotkeyDocument::parse(SAMPLE.as_bytes()).unwrap();
        document.entries[5].value = "shift + F".into();
        let rendered = document.render();
        assert!(rendered.contains("Previous Key: shift + F\r\n"));
        assert!(rendered.contains("Next Key: 'W'\r\n"));
    }

    #[test]
    fn preset_file_name_is_sanitized() {
        assert_eq!(
            safe_preset_file_name("  Bộ phím / Test  "),
            "Bộ-phím-Test.json"
        );
        assert_eq!(safe_preset_file_name("../../"), "preset.json");
    }

    #[test]
    fn hotkey_spacing_is_normalized() {
        assert_eq!(clean_hotkey(" ctrl+ shift +Q "), "ctrl + shift + Q");
    }

    #[test]
    fn spine_process_detection_ignores_hotkey_studio() {
        assert!(is_spine_process_name("Spine.exe"));
        assert!(is_spine_process_name("Spine-4.2.17.exe"));
        assert!(!is_spine_process_name("spine-hotkey-studio.exe"));
        assert!(!is_spine_process_name("spine-launcher.exe"));
    }

    #[test]
    fn current_spine_file_round_trips_when_present() {
        let Some(home) = std::env::var_os("USERPROFILE") else {
            return;
        };
        let path = PathBuf::from(home).join("Spine").join("hotkeys.txt");
        let Ok(bytes) = fs::read(path) else {
            return;
        };
        let document = HotkeyDocument::parse(&bytes).unwrap();
        assert_eq!(document.render().as_bytes(), bytes);
    }

    #[test]
    fn atomic_replace_updates_target() {
        let directory =
            std::env::temp_dir().join(format!("spine-hotkey-studio-test-{}", std::process::id()));
        fs::create_dir_all(&directory).unwrap();
        let path = directory.join("hotkeys.txt");
        fs::write(&path, b"old").unwrap();
        write_atomic(&path, b"new").unwrap();
        assert_eq!(fs::read(&path).unwrap(), b"new");
        fs::remove_dir_all(directory).unwrap();
    }
}
