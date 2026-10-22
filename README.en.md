# Onion MC Launcher

[简体中文](README.md) | [English](README.en.md)

**A free, open-source, community-oriented launcher for Minecraft: Java Edition.**

Current release: [v0.2.3](https://github.com/Pomelene/Onion-MC-Launcher/releases/tag/v0.2.3). On Windows, download the ZIP from Releases, extract it, and run `OnionMinecraftLauncher.exe`.

**v0.2.3 focuses on UI and interaction improvements**: shared rounded selection popups, a redesigned color picker and home launch button, improved alignment and wider path fields. It also refines transparency sliders, numeric inputs and visible units, adds bold text and wallpaper coverage options, and fixes background redraw issues when resizing. Welcome text is off by default and can be customized in Appearance settings.

The application is named **Onion Minecraft Launcher**. Built with Python and PySide6 / Qt, it aims to make instance management, game installation and content management straightforward. The project is developed as a free community resource, without a business model based on selling the launcher, accounts or game assets. Feedback and contributions are welcome.

The source is available under the [MIT License](LICENSE). The project's community mission adds no restrictions beyond that license. This is an independent community project, unaffiliated with Mojang, Microsoft or other launchers.

## Features

- Qt interface, instance selection, background downloads, cancellation and logs.
- Installation workflows for vanilla Minecraft, Fabric, Quilt, Forge, NeoForge and OptiFine.
- Management of mods, resource packs, shaders, and Modrinth / CurseForge modpacks.
- World backups, restoration and recoverable file removal.
- Account management, offline profiles, external authentication and Microsoft account authorization workflows.
- Per-instance settings, Java selection and launch arguments.
- Automatic settings persistence and restoration of the last selected instance; custom title bars for the main window and launcher dialogs.
- Dark/light themes, accent colors, bold text, separate text and window-surface transparency, and custom home wallpaper with display modes.

For Microsoft account authorization and publisher application configuration, see the [Microsoft login guide (Chinese)](docs/microsoft-auth.md). Players authorize through Microsoft's official website; publisher application setup is separate from player sign-in.

## Run from source

The primary development environment is Windows with Python 3.13.

```powershell
git clone https://github.com/Pomelene/Onion-MC-Launcher.git
cd Onion-MC-Launcher
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

The default game directory is `F:\.minecraft`. Change it to your own game directory in Settings. Settings, account records, instance display names and per-instance overrides are stored in `onionmcl.json` next to the launcher; Windows marks this file as hidden. Saved account tokens use Windows user-bound encryption. On first run, the launcher migrates the four legacy configuration files from the adjacent `config/` directory and keeps the originals. Games, worlds, Java runtimes and logs remain separate.

New EXE builds are placed in the project's `release/` directory. Copying only the EXE to a new directory, without `onionmcl.json`, starts with default settings. Include the hidden file in a private backup if you want to preserve your settings. Windows account tokens are bound to the original Windows user; moving to another machine or user may require signing in again. Do not upload this configuration file publicly.

Settings save automatically. Instances follow Settings → Global game settings by default, showing inherited values as disabled controls. Enable independent settings for the current instance to edit only that instance, without changing global defaults or other instances. Disabling the option removes that instance's overrides and restores inheritance. Java detection and downloads are grouped under Java management in the Settings sidebar; the Java path field selects the runtime used by the game.

The repository includes no Minecraft game files, Java runtimes, player accounts, access tokens or developer machine configuration. Users must obtain game access and third-party content permissions separately; the source license does not grant a Minecraft license.

## Tests and builds

```powershell
New-Item -ItemType Directory -Force tmp,docs/screens
python -X utf8 tests/run_all.py
python -X utf8 scripts/check_qt_ui.py
```

See the [development guide (Chinese)](docs/development.md) for Windows builds, project structure and dependencies. The repository provides a blank Microsoft publisher application template, excluding the developer's application configuration and authentication data.

## Open source and contributions

- This project is free, open source and community-oriented. Use and modify the code under the MIT License.
- Issues and pull requests are welcome; see [Contributing](CONTRIBUTING.md).
- HMCL, PCL and Axolotl informed workflow and interaction references; see [Third-party notices](THIRD_PARTY_NOTICES.md).
- Do not include accounts, passwords, tokens, private configuration or unredacted logs in issues, pull requests or commits. See [Security](SECURITY.md).
