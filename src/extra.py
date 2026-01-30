#!/usr/bin/env python3
"""
Post-Processor Module for HATSKit Pro v1.2.8
Handles post-extraction configuration of exosphere.ini and hosts files
Based on HATSIFY's main.c functionality
"""

import os
from pathlib import Path
from tkinter import messagebox

# Configuration file templates
EXOSPHERE_OFFLINE = """[exosphere]
debugmode=1
debugmode_user=0
disable_user_exception_handlers=0
enable_user_pmu_access=0
blank_prodinfo_sysmmc=1
blank_prodinfo_emummc=1
allow_writing_to_cal_sysmmc=0
log_port=0
log_baud_rate=115200
log_inverted=0
"""

EXOSPHERE_SYSMMC_ONLINE = """[exosphere]
debugmode=1
debugmode_user=0
disable_user_exception_handlers=0
enable_user_pmu_access=0
blank_prodinfo_sysmmc=0
blank_prodinfo_emummc=1
allow_writing_to_cal_sysmmc=0
log_port=0
log_baud_rate=115200
log_inverted=0
"""

EXOSPHERE_EMUMMC_ONLINE = """[exosphere]
debugmode=1
debugmode_user=0
disable_user_exception_handlers=0
enable_user_pmu_access=0
blank_prodinfo_sysmmc=1
blank_prodinfo_emummc=0
allow_writing_to_cal_sysmmc=0
log_port=0
log_baud_rate=115200
log_inverted=0
"""

EXOSPHERE_FULL_ONLINE = """[exosphere]
debugmode=1
debugmode_user=0
disable_user_exception_handlers=0
enable_user_pmu_access=0
blank_prodinfo_sysmmc=0
blank_prodinfo_emummc=0
allow_writing_to_cal_sysmmc=0
log_port=0
log_baud_rate=115200
log_inverted=0
"""

HOSTS_BLOCK_ALL = """# Nintendo Servers
127.0.0.1 *nintendo.*
127.0.0.1 *nintendoswitch.*
127.0.0.1 *.nintendo.com
127.0.0.1 *.nintendo.net
127.0.0.1 *.nintendo.jp
127.0.0.1 *.nintendo.co.jp
127.0.0.1 *.nintendo.co.uk
127.0.0.1 *.nintendo-europe.com
127.0.0.1 *.nintendowifi.net
127.0.0.1 *.nintendo.es
127.0.0.1 *.nintendo.co.kr
127.0.0.1 *.nintendo.tw
127.0.0.1 *.nintendo.com.hk
127.0.0.1 *.nintendo.com.au
127.0.0.1 *.nintendo.co.nz
127.0.0.1 *.nintendo.at
127.0.0.1 *.nintendo.be
127.0.0.1 *.nintendods.cz
127.0.0.1 *.nintendo.dk
127.0.0.1 *.nintendo.de
127.0.0.1 *.nintendo.fi
127.0.0.1 *.nintendo.fr
127.0.0.1 *.nintendo.gr
127.0.0.1 *.nintendo.hu
127.0.0.1 *.nintendo.it
127.0.0.1 *.nintendo.nl
127.0.0.1 *.nintendo.no
127.0.0.1 *.nintendo.pt
127.0.0.1 *.nintendo.ru
127.0.0.1 *.nintendo.co.za
127.0.0.1 *.nintendo.se
127.0.0.1 *.nintendo.ch
127.0.0.1 *.nintendoswitch.com
127.0.0.1 *.nintendoswitch.com.cn
127.0.0.1 *.nintendoswitch.cn
127.0.0.1 receive-*.dg.srv.nintendo.net
127.0.0.1 receive-*.er.srv.nintendo.net
# Nintendo CDN
95.216.149.205 conntest.nintendowifi.net
95.216.149.205 ctest.cdn.nintendo.net
"""

HOSTS_OPEN = """# No Nintendo server blocks
"""


class PostProcessor:
    """Handles post-extraction configuration of Switch CFW files"""

    def __init__(self, gui):
        self.gui = gui

    def get_file_paths(self, sd_path):
        """Get the paths for configuration files on the SD card"""
        sd_path = Path(sd_path)
        return {
            'exosphere': sd_path / 'exosphere.ini',
            'hosts_default': sd_path / 'atmosphere' / 'hosts' / 'default.txt',
            'hosts_sysmmc': sd_path / 'atmosphere' / 'hosts' / 'sysmmc.txt',
            'hosts_emummc': sd_path / 'atmosphere' / 'hosts' / 'emummc.txt',
            'sys_settings': sd_path / 'atmosphere' / 'config' / 'system_settings.ini',
            'hekate_ipl': sd_path / 'bootloader' / 'hekate_ipl.ini'
        }

    def detect_all_settings(self, sd_path):
        """Auto-detect all current settings from SD card"""
        if not sd_path:
            return None

        paths = self.get_file_paths(sd_path)

        # Check if essential files exist
        if not paths['exosphere'].exists():
            return None

        result = {
            'network_mode': self.detect_network_mode(sd_path),
            'hekate_config': self.detect_hekate_config(sd_path),
            'usb30_enabled': self.detect_usb30_setting(sd_path)
        }

        return result

    def detect_network_mode(self, sd_path):
        """Detect current network mode configuration"""
        paths = self.get_file_paths(sd_path)

        if not paths['exosphere'].exists():
            return None

        sys_online = False
        emu_online = False

        # Check sysmmc.txt
        sysmmc_content = self.read_file(paths['hosts_sysmmc'])
        if sysmmc_content and "# No Nintendo server blocks" in sysmmc_content:
            sys_online = True

        # Check emummc.txt
        emummc_content = self.read_file(paths['hosts_emummc'])
        if emummc_content and "# No Nintendo server blocks" in emummc_content:
            emu_online = True

        # Determine mode
        if sys_online and emu_online:
            return 'both_online'
        elif sys_online:
            return 'sysmmc_online'
        elif emu_online:
            return 'emummc_online'
        else:
            return 'default'

    def detect_hekate_config(self, sd_path):
        """Detect current Hekate boot menu configuration"""
        paths = self.get_file_paths(sd_path)
        hekate_path = paths['hekate_ipl']

        if not hekate_path.exists():
            return None

        content = self.read_file(hekate_path)
        if not content:
            return None

        entries = self.parse_hekate_ini(content)

        return {
            'ofw': entries['ofw'] is not None and not entries['ofw'].lstrip().startswith('#'),
            'semistock': entries['semistock'] is not None and not entries['semistock'].lstrip().startswith('#'),
            'sysmmc': entries['sysmmc'] is not None and not entries['sysmmc'].lstrip().startswith('#'),
            'emummc': entries['emummc'] is not None and not entries['emummc'].lstrip().startswith('#')
        }

    def detect_usb30_setting(self, sd_path):
        """Detect current USB 3.0 setting from system_settings.ini"""
        paths = self.get_file_paths(sd_path)

        if not paths['sys_settings'].exists():
            return None

        content = self.read_file(paths['sys_settings'])
        if not content:
            return None

        # Look for USB 3.0 setting
        if 'usb30_force_enabled = u8!0x1' in content:
            return True
        elif 'usb30_force_enabled = u8!0x0' in content:
            return False
        else:
            # Setting doesn't exist, default is disabled
            return False

    def update_usb30_setting(self, sys_settings_path, enable_usb30):
        """Update USB 3.0 settings in system_settings.ini"""
        content = self.read_file(sys_settings_path)

        if not content:
            return False

        # Look for existing USB 3.0 setting
        if 'usb30_force_enabled = u8!0x' in content:
            # Replace existing setting
            content = content.replace(
                'usb30_force_enabled = u8!0x0',
                f'usb30_force_enabled = u8!0x{"1" if enable_usb30 else "0"}'
            )
            content = content.replace(
                'usb30_force_enabled = u8!0x1',
                f'usb30_force_enabled = u8!0x{"1" if enable_usb30 else "0"}'
            )
        else:
            # Add the setting (append to file with proper formatting)
            if not content.endswith('\n'):
                content += '\n'
            content += f'\n; Enable USB 3.0 superspeed for homebrew\n'
            content += f'; 0 = USB 3.0 support is system default (usually disabled), 1 = USB 3.0 support is enabled.\n'
            content += f'usb30_force_enabled = u8!0x{"1" if enable_usb30 else "0"}\n'

        return self.write_file(sys_settings_path, content)

    def write_file(self, path, content):
        """Write content to a file, creating directories if needed"""
        try:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"Error writing {path}: {e}")
            return False

    def read_file(self, path):
        """Read content from a file"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"Error reading {path}: {e}")
            return None

    def save_all_settings(self, sd_path, network_mode, enable_ofw, enable_semistock, enable_sysmmc, enable_emummc, enable_usb30):
        """Save all settings at once: network mode, hekate config, and USB 3.0"""
        if not sd_path:
            self.gui.show_custom_info("Error", "Please set SD card path first", width=400, height=180)
            return False

        paths = self.get_file_paths(sd_path)
        results = []
        all_success = True

        # 1. Apply Network Mode
        if network_mode == 'default':
            success = self._apply_default_network(paths, results)
        elif network_mode == 'sysmmc_online':
            success = self._apply_sysmmc_online_network(paths, results)
        elif network_mode == 'emummc_online':
            success = self._apply_emummc_online_network(paths, results)
        elif network_mode == 'both_online':
            success = self._apply_both_online_network(paths, results)
        else:
            success = False

        if not success:
            all_success = False

        # 2. Apply Hekate Boot Menu Config
        if not (enable_ofw or enable_semistock or enable_sysmmc or enable_emummc):
            results.append("✗ Hekate Config: At least one option must be enabled")
            all_success = False
        else:
            hekate_path = paths['hekate_ipl']
            if hekate_path.exists():
                content = self.read_file(hekate_path)
                if content:
                    entries = self.parse_hekate_ini(content)
                    new_content = self.build_hekate_ini(entries, enable_ofw, enable_semistock, enable_sysmmc, enable_emummc)
                    if self.write_file(hekate_path, new_content):
                        results.append("✓ Hekate Boot Menu: Updated")
                    else:
                        results.append("✗ Hekate Boot Menu: Failed to write")
                        all_success = False
                else:
                    results.append("✗ Hekate Boot Menu: Failed to read")
                    all_success = False
            else:
                results.append("✗ Hekate Boot Menu: File not found")
                all_success = False

        # 3. Apply USB 3.0 Setting
        if paths['sys_settings'].exists():
            if self.update_usb30_setting(paths['sys_settings'], enable_usb30):
                usb_status = "Enabled" if enable_usb30 else "Disabled"
                results.append(f"✓ USB 3.0: {usb_status}")
            else:
                results.append("✗ USB 3.0: Failed to update")
                all_success = False
        else:
            results.append("✗ USB 3.0: system_settings.ini not found")
            all_success = False

        # Show results
        result_text = "\n".join(results)
        if all_success:
            self.gui.show_custom_info(
                "All Settings Applied Successfully",
                f"All configurations have been saved to SD card!\n\n{result_text}",
                width=500,
                height=300
            )
        else:
            self.gui.show_custom_info(
                "Settings Applied with Errors",
                f"Some settings failed to apply:\n\n{result_text}",
                width=500,
                height=300
            )

        return all_success

    def _apply_default_network(self, paths, results):
        """Apply default network configuration (both offline)"""
        success = True
        if self.write_file(paths['exosphere'], EXOSPHERE_OFFLINE):
            results.append("✓ Network: Both offline (default)")
        else:
            results.append("✗ Network: Failed to write exosphere.ini")
            success = False

        for host_file, name in [(paths['hosts_default'], 'default.txt'),
                                (paths['hosts_sysmmc'], 'sysmmc.txt'),
                                (paths['hosts_emummc'], 'emummc.txt')]:
            if not self.write_file(host_file, HOSTS_BLOCK_ALL):
                success = False

        if paths['sys_settings'].exists():
            self.update_dns_mitm_settings(paths['sys_settings'], True)

        return success

    def _apply_sysmmc_online_network(self, paths, results):
        """Apply sysMMC online network configuration"""
        success = True
        if self.write_file(paths['exosphere'], EXOSPHERE_SYSMMC_ONLINE):
            results.append("✓ Network: sysMMC online")
        else:
            results.append("✗ Network: Failed to write exosphere.ini")
            success = False

        if not self.write_file(paths['hosts_sysmmc'], HOSTS_OPEN):
            success = False
        if not self.write_file(paths['hosts_emummc'], HOSTS_BLOCK_ALL):
            success = False
        if not self.write_file(paths['hosts_default'], HOSTS_BLOCK_ALL):
            success = False

        if paths['sys_settings'].exists():
            self.update_dns_mitm_settings(paths['sys_settings'], False)

        return success

    def _apply_emummc_online_network(self, paths, results):
        """Apply emuMMC online network configuration"""
        success = True
        if self.write_file(paths['exosphere'], EXOSPHERE_EMUMMC_ONLINE):
            results.append("✓ Network: emuMMC online")
        else:
            results.append("✗ Network: Failed to write exosphere.ini")
            success = False

        if not self.write_file(paths['hosts_emummc'], HOSTS_OPEN):
            success = False
        if not self.write_file(paths['hosts_sysmmc'], HOSTS_BLOCK_ALL):
            success = False
        if not self.write_file(paths['hosts_default'], HOSTS_BLOCK_ALL):
            success = False

        if paths['sys_settings'].exists():
            self.update_dns_mitm_settings(paths['sys_settings'], False)

        return success

    def _apply_both_online_network(self, paths, results):
        """Apply both online network configuration"""
        success = True
        if self.write_file(paths['exosphere'], EXOSPHERE_FULL_ONLINE):
            results.append("✓ Network: Both online (HIGH RISK)")
        else:
            results.append("✗ Network: Failed to write exosphere.ini")
            success = False

        for host_file in [paths['hosts_sysmmc'], paths['hosts_emummc'], paths['hosts_default']]:
            if not self.write_file(host_file, HOSTS_OPEN):
                success = False

        if paths['sys_settings'].exists():
            self.update_dns_mitm_settings(paths['sys_settings'], False)

        return success

    def update_dns_mitm_settings(self, sys_settings_path, enable_mitm):
        """Update DNS MITM settings in system_settings.ini"""
        content = self.read_file(sys_settings_path)

        if not content:
            return False

        # Look for the DNS MITM settings
        if 'enable_dns_mitm = u8!0x' in content:
            content = content.replace(
                'enable_dns_mitm = u8!0x0',
                f'enable_dns_mitm = u8!0x{"1" if enable_mitm else "0"}'
            )
            content = content.replace(
                'enable_dns_mitm = u8!0x1',
                f'enable_dns_mitm = u8!0x{"1" if enable_mitm else "0"}'
            )

        if 'add_defaults_to_dns_hosts = u8!0x' in content:
            content = content.replace(
                'add_defaults_to_dns_hosts = u8!0x0',
                f'add_defaults_to_dns_hosts = u8!0x{"1" if enable_mitm else "0"}'
            )
            content = content.replace(
                'add_defaults_to_dns_hosts = u8!0x1',
                f'add_defaults_to_dns_hosts = u8!0x{"1" if enable_mitm else "0"}'
            )

        return self.write_file(sys_settings_path, content)

    def set_default_config(self, sd_path):
        """Set default configuration: Both offline (safest mode)"""
        if not sd_path:
            self.gui.show_custom_info("Error", "Please set SD card path first", width=400, height=180)
            return

        paths = self.get_file_paths(sd_path)
        results = []

        # Write exosphere.ini
        if self.write_file(paths['exosphere'], EXOSPHERE_OFFLINE):
            results.append("✓ exosphere.ini: Both offline")
        else:
            results.append("✗ exosphere.ini: Failed")

        # Write all hosts files to block
        if self.write_file(paths['hosts_default'], HOSTS_BLOCK_ALL):
            results.append("✓ default.txt: Blocked")
        else:
            results.append("✗ default.txt: Failed")

        if self.write_file(paths['hosts_sysmmc'], HOSTS_BLOCK_ALL):
            results.append("✓ sysmmc.txt: Blocked")
        else:
            results.append("✗ sysmmc.txt: Failed")

        if self.write_file(paths['hosts_emummc'], HOSTS_BLOCK_ALL):
            results.append("✓ emummc.txt: Blocked")
        else:
            results.append("✗ emummc.txt: Failed")

        # Enable DNS MITM
        if paths['sys_settings'].exists():
            if self.update_dns_mitm_settings(paths['sys_settings'], True):
                results.append("✓ DNS MITM: Enabled")
            else:
                results.append("✗ DNS MITM: Failed")

        result_text = "\n".join(results)
        self.gui.show_custom_info(
            "Default Configuration Applied",
            f"Both sysMMC CFW and emuMMC are now offline.\n\n{result_text}",
            width=500,
            height=350
        )

    def set_sysmmc_online(self, sd_path):
        """Set sysMMC CFW online, emuMMC offline"""
        if not sd_path:
            self.gui.show_custom_info("Error", "Please set SD card path first", width=400, height=180)
            return

        # Show warning
        confirm = self.gui.show_custom_confirm(
            "WARNING - BAN RISK",
            "This mode allows sysMMC CFW to connect to Nintendo online services.\n\n"
            "• Your REAL console identity will be visible to Nintendo\n"
            "• If detected with illegal content, your console may be banned\n"
            "• emuMMC will remain safely offline\n\n"
            "Proceed at your own risk!",
            yes_text="Proceed",
            no_text="Cancel",
            style="danger",
            width=500,
            height=430
        )

        if not confirm:
            return

        paths = self.get_file_paths(sd_path)
        results = []

        # Write exosphere.ini
        if self.write_file(paths['exosphere'], EXOSPHERE_SYSMMC_ONLINE):
            results.append("✓ exosphere.ini: sysMMC online")
        else:
            results.append("✗ exosphere.ini: Failed")

        # sysMMC hosts open
        if self.write_file(paths['hosts_sysmmc'], HOSTS_OPEN):
            results.append("✓ sysmmc.txt: Open")
        else:
            results.append("✗ sysmmc.txt: Failed")

        # emuMMC and default hosts blocked
        if self.write_file(paths['hosts_emummc'], HOSTS_BLOCK_ALL):
            results.append("✓ emummc.txt: Blocked")
        else:
            results.append("✗ emummc.txt: Failed")

        if self.write_file(paths['hosts_default'], HOSTS_BLOCK_ALL):
            results.append("✓ default.txt: Blocked")
        else:
            results.append("✗ default.txt: Failed")

        # Disable DNS MITM
        if paths['sys_settings'].exists():
            if self.update_dns_mitm_settings(paths['sys_settings'], False):
                results.append("✓ DNS MITM: Disabled")
            else:
                results.append("✗ DNS MITM: Failed")

        result_text = "\n".join(results)
        self.gui.show_custom_info(
            "sysMMC Online Configuration Applied",
            f"sysMMC CFW can now connect to Nintendo.\nemuMMC remains protected.\n\n{result_text}",
            width=500,
            height=350
        )

    def set_emummc_online(self, sd_path):
        """Set emuMMC online, sysMMC CFW offline"""
        if not sd_path:
            self.gui.show_custom_info("Error", "Please set SD card path first", width=400, height=180)
            return

        # Show warning
        confirm = self.gui.show_custom_confirm(
            "WARNING - BAN RISK",
            "This mode allows emuMMC to connect to Nintendo online services.\n\n"
            "• While your sysMMC CFW is protected, your console can still be banned\n"
            "• Nintendo may detect unauthorized modifications on emuMMC\n"
            "• Not recommended for emuMMC with illegal content or significant mods\n\n"
            "Proceed at your own risk!",
            yes_text="Proceed",
            no_text="Cancel",
            style="danger",
            width=500,
            height=460
        )

        if not confirm:
            return

        paths = self.get_file_paths(sd_path)
        results = []

        # Write exosphere.ini
        if self.write_file(paths['exosphere'], EXOSPHERE_EMUMMC_ONLINE):
            results.append("✓ exosphere.ini: emuMMC online")
        else:
            results.append("✗ exosphere.ini: Failed")

        # emuMMC hosts open
        if self.write_file(paths['hosts_emummc'], HOSTS_OPEN):
            results.append("✓ emummc.txt: Open")
        else:
            results.append("✗ emummc.txt: Failed")

        # sysMMC and default hosts blocked
        if self.write_file(paths['hosts_sysmmc'], HOSTS_BLOCK_ALL):
            results.append("✓ sysmmc.txt: Blocked")
        else:
            results.append("✗ sysmmc.txt: Failed")

        if self.write_file(paths['hosts_default'], HOSTS_BLOCK_ALL):
            results.append("✓ default.txt: Blocked")
        else:
            results.append("✗ default.txt: Failed")

        # Disable DNS MITM
        if paths['sys_settings'].exists():
            if self.update_dns_mitm_settings(paths['sys_settings'], False):
                results.append("✓ DNS MITM: Disabled")
            else:
                results.append("✗ DNS MITM: Failed")

        result_text = "\n".join(results)
        self.gui.show_custom_info(
            "emuMMC Online Configuration Applied",
            f"emuMMC can now connect to Nintendo.\nsysMMC CFW remains protected.\n\n{result_text}",
            width=500,
            height=350
        )

    def set_both_online(self, sd_path):
        """Set both sysMMC CFW and emuMMC online (MAXIMUM RISK)"""
        if not sd_path:
            self.gui.show_custom_info("Error", "Please set SD card path first", width=400, height=180)
            return

        # Show severe warning
        confirm = self.gui.show_custom_confirm(
            "SEVERE WARNING - MAXIMUM BAN RISK",
            "This mode allows sysMMC CFW and emuMMC full online access.\n\n"
            "• EXTREMELY HIGH RISK of console ban\n"
            "• No protection against Nintendo detecting modifications\n"
            "• Full prodinfo access - console identifiers will be visible\n"
            "• For advanced users only who fully understand the consequences\n\n"
            "Are you absolutely certain?",
            yes_text="Yes, Proceed",
            no_text="Cancel",
            style="danger",
            width=500,
            height=480
        )

        if not confirm:
            return

        paths = self.get_file_paths(sd_path)
        results = []

        # Write exosphere.ini
        if self.write_file(paths['exosphere'], EXOSPHERE_FULL_ONLINE):
            results.append("✓ exosphere.ini: Full online (no blanking)")
        else:
            results.append("✗ exosphere.ini: Failed")

        # All hosts files open
        if self.write_file(paths['hosts_sysmmc'], HOSTS_OPEN):
            results.append("✓ sysmmc.txt: Open")
        else:
            results.append("✗ sysmmc.txt: Failed")

        if self.write_file(paths['hosts_emummc'], HOSTS_OPEN):
            results.append("✓ emummc.txt: Open")
        else:
            results.append("✗ emummc.txt: Failed")

        if self.write_file(paths['hosts_default'], HOSTS_OPEN):
            results.append("✓ default.txt: Open")
        else:
            results.append("✗ default.txt: Failed")

        # Disable DNS MITM
        if paths['sys_settings'].exists():
            if self.update_dns_mitm_settings(paths['sys_settings'], False):
                results.append("✓ DNS MITM: Disabled")
            else:
                results.append("✗ DNS MITM: Failed")

        result_text = "\n".join(results)
        self.gui.show_custom_info(
            "Maximum Risk Configuration Applied",
            f"Both sysMMC CFW and emuMMC can now connect to Nintendo.\n\n"
            f"MAXIMUM BAN RISK: No protection is active!\n\n{result_text}",
            width=500,
            height=400
        )

    def show_current_config(self, sd_path):
        """Display the current configuration status"""
        if not sd_path:
            self.gui.show_custom_info("Error", "Please set SD card path first", width=400, height=180)
            return

        paths = self.get_file_paths(sd_path)

        # Check if files exist
        if not paths['exosphere'].exists():
            self.gui.show_custom_info(
                "Files Not Found",
                "Configuration files not found on SD card.\n\n"
                "Please ensure you've extracted a HATS pack to this SD card first.",
                width=450,
                height=250
            )
            return

        # Determine current mode
        sys_online = False
        emu_online = False
        dns_mitm = False

        # Check sysmmc.txt
        sysmmc_content = self.read_file(paths['hosts_sysmmc'])
        if sysmmc_content and "# No Nintendo server blocks" in sysmmc_content:
            sys_online = True

        # Check emummc.txt
        emummc_content = self.read_file(paths['hosts_emummc'])
        if emummc_content and "# No Nintendo server blocks" in emummc_content:
            emu_online = True

        # Check DNS MITM
        if paths['sys_settings'].exists():
            sys_settings_content = self.read_file(paths['sys_settings'])
            if sys_settings_content and "enable_dns_mitm = u8!0x1" in sys_settings_content:
                dns_mitm = True

        # Determine mode
        if sys_online and emu_online:
            mode = "BOTH ONLINE (HIGH RISK)"
            mode_desc = "Both sysMMC CFW and emuMMC can connect to Nintendo services."
        elif sys_online:
            mode = "sysMMC CFW ONLINE"
            mode_desc = "sysMMC CFW can connect to Nintendo, emuMMC is offline."
        elif emu_online:
            mode = "emuMMC ONLINE"
            mode_desc = "emuMMC can connect to Nintendo, sysMMC CFW is offline."
        else:
            mode = "BOTH OFFLINE (DEFAULT)"
            mode_desc = "Both sysMMC CFW and emuMMC are offline from Nintendo services."

        dns_status = "ENABLED - blocking active" if dns_mitm else "DISABLED - connections allowed"

        self.gui.show_custom_info(
            "Current Network Configuration",
            f"Current Mode: {mode}\n\n"
            f"{mode_desc}\n\n"
            f"DNS MITM: {dns_status}\n\n"
            f"Note: To change settings, use the Network Modes options above. "
            f"Your original files will be overwritten.",
            width=500,
            height=400
        )

    def parse_hekate_ini(self, content):
        """Parse hekate_ipl.ini content and extract boot entries"""
        entries = {
            'config': None,
            'ofw': None,
            'semistock': None,
            'sysmmc': None,
            'emummc': None,
            'other': []
        }

        # Use splitlines to handle different line endings gracefully
        lines = content.split('\n')
        current_entry = None
        current_lines = []

        for line in lines:
            stripped_line = line.strip()
            if stripped_line.startswith('[') or (stripped_line.startswith('#[') and stripped_line.endswith(']')):
                # Save previous entry
                if current_entry:
                    entry_text = '\n'.join(current_lines)
                    if current_entry == 'config':
                        entries['config'] = entry_text
                    elif current_entry == 'ofw':
                        entries['ofw'] = entry_text
                    elif current_entry == 'semistock':
                        entries['semistock'] = entry_text
                    elif current_entry == 'sysmmc':
                        entries['sysmmc'] = entry_text
                    elif current_entry == 'emummc':
                        entries['emummc'] = entry_text
                    else:
                        entries['other'].append(entry_text)

                # Start new entry
                header = stripped_line.upper()
                current_lines = [line]

                if header.startswith('[CONFIG') or header.startswith('#[CONFIG'):
                    current_entry = 'config'
                elif 'STOCK' in header and 'OFW' in header:
                    current_entry = 'ofw'
                elif 'SEMI-STOCK' in header and 'SYSMMC' in header:
                    current_entry = 'semistock'
                elif 'CFW' in header and 'SYSMMC' in header:
                    current_entry = 'sysmmc'
                elif 'CFW' in header and 'EMUMMC' in header:
                    current_entry = 'emummc'
                else:
                    current_entry = 'other'
            else:
                current_lines.append(line)

        # Save last entry
        if current_entry:
            entry_text = '\n'.join(current_lines)
            if current_entry == 'config':
                entries['config'] = entry_text
            elif current_entry == 'ofw':
                entries['ofw'] = entry_text
            elif current_entry == 'semistock':
                entries['semistock'] = entry_text
            elif current_entry == 'sysmmc':
                entries['sysmmc'] = entry_text
            elif current_entry == 'emummc':
                entries['emummc'] = entry_text
            else:
                entries['other'].append(entry_text)

        return entries

    def build_hekate_ini(self, entries, enable_ofw, enable_semistock, enable_sysmmc, enable_emummc):
        """Build hekate_ipl.ini content from entries"""
        sections = []

        # Always add the [config] block first if it exists
        if entries['config']:
            # Ensure it's not commented out
            sections.append('\n'.join(line.lstrip('#') for line in entries['config'].splitlines()))

        # Add OFW entry (no network mode modifications needed - always online)
        if entries['ofw']:
            uncommented_section = '\n'.join(line.lstrip('#') for line in entries['ofw'].splitlines())
            if enable_ofw:
                sections.append(uncommented_section)
            else:
                sections.append('\n'.join('#' + line for line in uncommented_section.splitlines()))

        # Add enabled entries
        if entries['semistock']:
            # First, ensure the section is fully uncommented
            uncommented_section = '\n'.join(line.lstrip('#') for line in entries['semistock'].splitlines())
            if enable_semistock:
                sections.append(uncommented_section)
            else:
                # Then, comment out every line of the clean section
                sections.append('\n'.join('#' + line for line in uncommented_section.splitlines()))

        if entries['sysmmc']:
            uncommented_section = '\n'.join(line.lstrip('#') for line in entries['sysmmc'].splitlines())
            if enable_sysmmc:
                sections.append(uncommented_section)
            else:
                sections.append('\n'.join('#' + line for line in uncommented_section.splitlines()))

        if entries['emummc']:
            uncommented_section = '\n'.join(line.lstrip('#') for line in entries['emummc'].splitlines())
            if enable_emummc:
                sections.append(uncommented_section)
            else:
                sections.append('\n'.join('#' + line for line in uncommented_section.splitlines()))

        # Add other entries
        for entry in entries['other']:
            sections.append(entry)

        # Join with double newlines
        content = '\n\n'.join(sections)

        # Ensure file ends with newline
        if not content.endswith('\n'):
            content += '\n'

        return content

    def apply_hekate_config(self, sd_path, enable_ofw, enable_semistock, enable_sysmmc, enable_emummc):
        """Apply Hekate boot menu configuration"""
        if not sd_path:
            self.gui.show_custom_info("Error", "Please set SD card path first", width=400, height=180)
            return

        # Validate that at least one option is enabled
        if not (enable_ofw or enable_semistock or enable_sysmmc or enable_emummc):
            self.gui.show_custom_info(
                "Invalid Configuration",
                "At least one boot option must be enabled.\n\n"
                "The Switch needs at least one option to boot!",
                width=450,
                height=250
            )
            return

        paths = self.get_file_paths(sd_path)
        hekate_path = paths['hekate_ipl']

        # Check if file exists
        if not hekate_path.exists():
            self.gui.show_custom_info(
                "File Not Found",
                f"Could not find hekate_ipl.ini at:\n{hekate_path}\n\n"
                "Please ensure you've extracted a HATS pack to this SD card first.",
                width=500,
                height=250
            )
            return

        # Read current content
        content = self.read_file(hekate_path)
        if not content:
            self.gui.show_custom_info("Error", "Failed to read hekate_ipl.ini", width=400)
            return

        # Parse entries
        entries = self.parse_hekate_ini(content)

        # Build new content
        new_content = self.build_hekate_ini(entries, enable_ofw, enable_semistock, enable_sysmmc, enable_emummc)

        # Write to file
        if self.write_file(hekate_path, new_content):
            enabled_options = []
            if enable_ofw:
                enabled_options.append("100% Stock OFW")
            if enable_semistock:
                enabled_options.append("Semi-Stock (SYSMMC)")
            if enable_sysmmc:
                enabled_options.append("CFW (SYSMMC)")
            if enable_emummc:
                enabled_options.append("CFW (EMUMMC)")

            options_text = "\n".join([f"  • {opt}" for opt in enabled_options])

            self.gui.show_custom_info(
                "Hekate Configuration Applied",
                f"Boot menu has been updated successfully!\n\n"
                f"Enabled boot options:\n{options_text}\n\n"
                f"The changes will take effect on next boot.",
                width=500,
                height=350
            )
        else:
            self.gui.show_custom_info(
                "Error",
                "Failed to write hekate_ipl.ini\n\n"
                "Please check SD card permissions.",
                width=450,
                height=250
            )

    def load_hekate_config(self, sd_path, semistock_var, sysmmc_var, emummc_var):
        """Load current Hekate boot menu configuration"""
        if not sd_path:
            self.gui.show_custom_info("Error", "Please set SD card path first", width=400, height=180)
            return

        paths = self.get_file_paths(sd_path)
        hekate_path = paths['hekate_ipl']

        # Check if file exists
        if not hekate_path.exists():
            self.gui.show_custom_info(
                "File Not Found",
                f"Could not find hekate_ipl.ini at:\n{hekate_path}\n\n"
                "Please ensure you've extracted a HATS pack to this SD card first.",
                width=500,
                height=250
            )
            return

        # Read content
        content = self.read_file(hekate_path)
        if not content:
            self.gui.show_custom_info("Error", "Failed to read hekate_ipl.ini", width=400)
            return

        # Parse entries
        entries = self.parse_hekate_ini(content)

        # Update UI variables
        semistock_var.set(entries['semistock'] is not None and not entries['semistock'].lstrip().startswith('#'))
        sysmmc_var.set(entries['sysmmc'] is not None and not entries['sysmmc'].lstrip().startswith('#'))
        emummc_var.set(entries['emummc'] is not None and not entries['emummc'].lstrip().startswith('#'))

        # Show info
        enabled_options = []
        if semistock_var.get():
            enabled_options.append("Semi-Stock (SYSMMC)")
        if sysmmc_var.get():
            enabled_options.append("CFW (SYSMMC)")
        if emummc_var.get():
            enabled_options.append("CFW (EMUMMC)")

        if enabled_options:
            options_text = "\n".join([f"  • {opt}" for opt in enabled_options])
            self.gui.show_custom_info(
                "Current Hekate Configuration",
                f"Currently enabled boot options:\n\n{options_text}",
                width=450,
                height=300
            )
        else:
            self.gui.show_custom_info(
                "Warning",
                "No standard boot options found in hekate_ipl.ini\n\n"
                "This may indicate a custom configuration.",
                width=450,
                height=250
            )
