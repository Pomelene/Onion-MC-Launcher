# Onion MC Launcher

[简体中文](README.md) | [English](README.en.md)

A free, open-source, community-oriented launcher for Minecraft Java Edition.

Onion brings game installation, instance management, and everyday tools into a simple, customizable interface. This is a nonprofit community project for learning and sharing. The launcher is free to use and does not provide a Minecraft license.

## Features

### Accounts and launching

- Microsoft accounts, offline accounts, and third-party authentication.
- Automatic discovery, selection, and download of suitable Java runtimes.
- Memory allocation, window dimensions, launch arguments, and game process priority.
- Global and per-instance settings, automatic saving, and remembered instance selection.
- Pre-launch environment checks, game logs, and basic crash diagnosis.

### Installation and instances

- Vanilla Minecraft, Fabric, Legacy Fabric, Forge, NeoForge, Quilt, and OptiFine installation.
- Multiple game folders and a combined instance overview.
- Instance search, favorites, tags, renaming, copying, and custom icons.
- In-place Fabric and Quilt loader changes for existing instances.
- Modrinth, CurseForge, and common MultiMC/Prism modpack imports.
- Modrinth modpack export with selectable content categories.

Support varies by loader and pack format. Packs with complex custom components may not be supported.

### Game content

- Search and download mods, resource packs, and shaders, with compatible file version selection.
- Required dependency installation and updates for installed mods.
- Individual mod toggling and bulk enabling or disabling of search results.
- World management, backups, export, and per-world data packs.
- Litematica and other schematic file management, including subfolders.
- Chronological screenshot browsing with multiselection, export, and removal.

### Workshop

- Local skin management, favorites, and a draggable, rotatable 3D preview.
- Skin uploads and cape synchronization and selection for Microsoft accounts.
- A local seed map with dimensions, coordinate navigation, zoom, and structure markers.

### Appearance and everyday use

- Dark, light, and system-following modes.
- Custom accent colors and wallpaper-based theme colors.
- Custom backgrounds, scaling modes, and background coverage.
- Separate UI, text, and background transparency controls.
- Font family, size, bold text, corner radius, blur, and animation duration settings.
- Custom home-page greetings.
- Download progress, task history, automatic launcher updates, and historical version selection.

## Editions

| Edition | Intended use |
| --- | --- |
| Standard | General game launching and management for everyone. |
| THUnion | The standard features plus a service directory for THUnion. Version numbers end in `-T`. |

Both editions are publicly available. THUnion is an unofficial, nonprofit community organization. Its services are not official Tsinghua University services.

## Download and use

Download the appropriate Windows x64 EXE from [Releases](https://github.com/Pomelene/Onion-MC-Launcher/releases), place it in your preferred launcher folder, and run it.

Settings are stored in the hidden `onionmcl.json` file beside the EXE. Logs, skins, and other supporting data are stored in the hidden `.onion` folder. Game files remain in your selected game folder. Keep the relevant files and folders when moving your installation.

Microsoft account credentials are encrypted for the current Windows user. Moving to another device or Windows user may require signing in again.

## Open source and acknowledgments

Onion is an independent Python/Qt launcher. Its development references the workflows, implementations, and interaction design of open-source projects including HMCL and Axolotl. Thank you to their developers and everyone who provides feedback, testing, and contributions.

The project's own code is licensed under the [MIT License](LICENSE). See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for third-party components and acknowledgments. The project license does not change the rights associated with third-party code, trademarks, or services.

This project is not affiliated with or partnered with Mojang Studios or Microsoft.

## Feedback and contributions

Bug reports, suggestions, and code contributions are welcome.

- [Report an issue or suggest a feature](https://github.com/Pomelene/Onion-MC-Launcher/issues)
- [Browse the source code](https://github.com/Pomelene/Onion-MC-Launcher)
- [Contributing](CONTRIBUTING.md) and [development guide (Chinese)](docs/development.md)

Include reproduction steps in your report. Remove account tokens, passwords, and other sensitive information before uploading screenshots or logs.
