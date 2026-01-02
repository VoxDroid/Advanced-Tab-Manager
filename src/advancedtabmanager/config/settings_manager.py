from PyQt6.QtCore import QSettings
import json
import os

class SettingsManager:
    def __init__(self):
        self.settings = QSettings("AdvancedTabManager", "Settings")

    def save_settings(self, ui_elements):
        """Save all settings from UI elements."""
        self.settings.setValue("url", ui_elements.get('url_input', '').text())
        self.settings.setValue("iterations", ui_elements.get('iterations_input', 0).value())
        self.settings.setValue("interval", ui_elements.get('interval_input', 1).value())
        self.settings.setValue("instances", ui_elements.get('instances_input', 1).value())
        self.settings.setValue("theme", ui_elements.get('theme_combo', 0).currentIndex())
        self.settings.setValue("font_size", ui_elements.get('font_size_spin', 12).value())
        self.settings.setValue("language", ui_elements.get('language_combo', 0).currentIndex())
        self.settings.setValue("headless", ui_elements.get('headless_checkbox', False).isChecked())
        self.settings.setValue("disable_gpu", ui_elements.get('disable_gpu_checkbox', False).isChecked())
        self.settings.setValue("incognito", ui_elements.get('incognito_checkbox', False).isChecked())
        self.settings.setValue("disable_extensions", ui_elements.get('disable_extensions_checkbox', False).isChecked())
        self.settings.setValue("start_maximized", ui_elements.get('start_maximized_checkbox', False).isChecked())
        self.settings.setValue("user_agent", ui_elements.get('user_agent_input', '').text())
        self.settings.setValue("use_proxy", ui_elements.get('proxy_checkbox', False).isChecked())
        self.settings.setValue("proxy_address", ui_elements.get('proxy_address_input', '').text())
        self.settings.setValue("additional_args", ui_elements.get('additional_args_input', '').toPlainText())
        self.settings.setValue("autostart", ui_elements.get('autostart_check', False).isChecked())
        self.settings.setValue("lock_window_size", ui_elements.get('lock_window_size_check', True).isChecked())

    def load_settings(self, ui_elements):
        """Load settings into UI elements."""
        ui_elements.get('url_input', lambda: None).setText(self.settings.value("url", "https://google.com/"))
        ui_elements.get('iterations_input', lambda: None).setValue(int(self.settings.value("iterations", 0)))
        ui_elements.get('interval_input', lambda: None).setValue(int(self.settings.value("interval", 1)))
        ui_elements.get('instances_input', lambda: None).setValue(int(self.settings.value("instances", 1)))
        ui_elements.get('theme_combo', lambda: None).setCurrentIndex(int(self.settings.value("theme", 0)))
        ui_elements.get('font_size_spin', lambda: None).setValue(int(self.settings.value("font_size", 12)))
        ui_elements.get('language_combo', lambda: None).setCurrentIndex(int(self.settings.value("language", 0)))
        ui_elements.get('headless_checkbox', lambda: None).setChecked(self.settings.value("headless", False, type=bool))
        ui_elements.get('disable_gpu_checkbox', lambda: None).setChecked(self.settings.value("disable_gpu", False, type=bool))
        ui_elements.get('incognito_checkbox', lambda: None).setChecked(self.settings.value("incognito", False, type=bool))
        ui_elements.get('disable_extensions_checkbox', lambda: None).setChecked(self.settings.value("disable_extensions", False, type=bool))
        ui_elements.get('start_maximized_checkbox', lambda: None).setChecked(self.settings.value("start_maximized", False, type=bool))
        ui_elements.get('user_agent_input', lambda: None).setText(self.settings.value("user_agent", ""))
        ui_elements.get('proxy_checkbox', lambda: None).setChecked(self.settings.value("use_proxy", False, type=bool))
        ui_elements.get('proxy_address_input', lambda: None).setText(self.settings.value("proxy_address", ""))
        ui_elements.get('additional_args_input', lambda: None).setPlainText(self.settings.value("additional_args", ""))
        if 'autostart_check' in ui_elements:
            ui_elements['autostart_check'].setChecked(self.settings.value("autostart", False, type=bool))
        if 'lock_window_size_check' in ui_elements:
            ui_elements['lock_window_size_check'].setChecked(self.settings.value("lock_window_size", True, type=bool))

    def export_settings(self, filepath):
        """Export settings to a JSON file."""
        settings_dict = {}
        for key in self.settings.allKeys():
            settings_dict[key] = self.settings.value(key)
        with open(filepath, 'w') as f:
            json.dump(settings_dict, f, indent=4)

    def import_settings(self, filepath):
        """Import settings from a JSON file."""
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                settings_dict = json.load(f)
            for key, value in settings_dict.items():
                self.settings.setValue(key, value)

    def get_setting(self, key, default=None):
        """Get a specific setting value."""
        return self.settings.value(key, default)

    def set_setting(self, key, value):
        """Set a specific setting value."""
        self.settings.setValue(key, value)