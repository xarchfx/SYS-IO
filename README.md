# SYS IO - Your PC Analyse Tool

**SYS IO** is a comprehensive system information and hardware monitoring tool that provides detailed insights into PC components and the current system status.

Developed by Arch (@xarchfx), this project combines a powerful Python backend with a modern, responsive web interface (HTML/CSS/JS) rendered via PyQt6.

## ✨ Features

* **Comprehensive Hardware Diagnostics:** Detailed information about the operating system, motherboard/BIOS, processor graphics card(s), memory, and storage drives.
* **Real-time Monitoring:** Live tracking of CPU and RAM usage, as well as temperature readings for processors and NVIDIA graphics cards.
* **Hardware IDs (HWID):** Quick access to device-specific identifiers such as MAC addresses, Machine GUIDs, System UUIDs, and Volume Serial Numbers.
* **Modern, Hybrid UI**

## 🛠️ Technologies

This project utilizes a hybrid approach:
* **Backend:** Python 3.15
* **Frontend Rendering:** PyQt6 (`QWebEngineView`, `QWebChannel`)
* **User Interface:** HTML, CSS, JavaScript, FontAwesome

## 🎮 Usage

Simply start the application. ( `.exe` )

Upon the launch on Windows, the app prompts for administrator privileges (UAC) by default, as these are required to read certain hardware IDs and BIOS information. This behavior can be disabled in the in-app settings.

## 👨‍💻 Author

**Arch / @xarchfx**

https://xarchfx.lol
