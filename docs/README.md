# Rhythia Kwest

> An autoplay bot for [Rhythia](https://rhythia.com/) that reads native `.sspm` map files and executes the notes in real-time.

---

## Screenshots

<!-- Startup banner & map info display -->
Startup banner:
![Startup Banner](../docs/screenshots/startup_banner.png)

<!-- Calibration wizard in action -->
Grid calibration wizard:
![Calibration Wizard](../docs/screenshots/calibration_wizard.png)

<!-- Live progress bar during playback -->
Live progress bar:
![Playback Progress](../docs/screenshots/playback_progress.png)

---

## Features

### Map Parsing
Loads any `.sspm` (Sound Space Plus Map) file, showing:
- Map name and mapper(s)
- Difficulty rating
- Total note count
- Map duration in seconds
- Whether the map uses quantum note positions

### Grid Calibration Wizard
On first launch or when passed the `--calibrate` flag, a wizard guides you through aligning the bot to your screen.

### Speed Adjustment
When executing the command, you can pass the flag `--speed` to adjust the speed of the playback to your desired one.

### Pause & Resume
You can press **ESC** to pause and ress **ESC** again to resume.

### Emergency Stop
If your PC is about to blow up, press **F3** at any time to immediately exit the tool.

### Live Progress Bar
A compact progress bar is printed to the terminal showing percentage completion and the raw note counter

### Persistent Configuration
All settings (grid position, timing offset, countdown duration, hotkeys) are stored in `utils/rhythia_config.json`. Manual edits to this file are respected on the next launch. Running `--calibrate` overwrites only the grid coordinates.

---
## Changelog
- **v-1.0.0** - Initial release.
- **v-pre-1.1.1** - Added audio handling and remaking of the calibration system.
- **v1.1.1** - Modularized code and added QoL feature.
- **v1.1.2** - A speed flag has been added to the playback command.
- **v1.2.0** - **Human mode has been added!** Your replay now looks way more human and will make you less likely to get banned.
 

## Requirements

- **Python 3.10+**
- **Windows** (DirectInput is Windows-only)

---

## Installation

**1. Clone the repository**

```bash
git clone https://github.com/AragonSprt/Rhythia-Kwest
cd Rhythia-Kwest
```

**2. (Recommended) Create a virtual environment**

```bash
python -m venv .venv
.venv\Scripts\activate
```

**3. Install dependencies**

```bash
pip install -r utils/requirements.txt
```

> **Note on `pysspm` vs `pysspm-rhythia`:**
> This project uses `pysspm-rhythia` (v2), which ships its own `pysspm` module internally. Do **not** install the legacy `pysspm` package alongside it, they will conflict. If you have the old package installed, remove it first:
> ```bash
> pip uninstall pysspm
> pip install pysspm-rhythia
> ```

---

## Usage

> [!WARNING]
> Careful! Inside Rhythia, you should change the Cursor settings from Relative to Absolute or else the bot WILL NOT work. Feel free to change back and forth between the two modes for when you use the tool.

### First run (calibration required)

```bash
python -m rhythia_autoplay runs/example.sspm --example_flag
```

On the first launch, the calibration wizard starts automatically.

### Standard playback

```bash
python -m rhythia_autoplay runs/example.sspm --example_flag
```

### Force re-calibration

```bash
python -m rhythia_autoplay runs/example.sspm --calibrate
```

### Apply a timing offset

```bash
# Delay all notes by 50 ms
python -m rhythia_autoplay runs/example.sspm --offset 50

# Fire all notes 30 ms earlier
python -m rhythia_autoplay runs/example.sspm --offset -30
```

### Override the countdown

```bash
python -m rhythia_autoplay runs/example.sspm --countdown 3
```

---

## Hotkeys

| Key     | Action               |
|---------|----------------------|
| `ESC`   | Pause / Resume       |
| `F3`    | Emergency stop       |
| `Ctrl+C`| Cancel before start  |

---

## Built by AragonSpirit - v1.2.0
