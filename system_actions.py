import os
import subprocess
import webbrowser


class SystemActions:
    def __init__(self, website_map, app_map):
        self.website_map = website_map
        self.app_map = app_map

    def handle_open_command(self, text):
        open_verbs = [
            "open ",
            "launch ",
            "start ",
            "run ",
            "show ",
            "go to ",
            "take me to ",
        ]

        if not any(verb in text for verb in open_verbs):
            return None

        for site_name, url in self.website_map.items():
            if site_name in text:
                return self.open_website(site_name, url)

        for app_name, app_path in self.app_map.items():
            if app_name in text:
                return self.open_application(app_name, app_path)

        return "I do not recognize that application or website yet, sir."

    def open_website(self, site_name, url):
        try:
            webbrowser.open(url)
            return f"Opening {site_name}, sir."
        except Exception:
            return f"I was unable to open {site_name}, sir."

    def open_application(self, app_name, app_path):
        try:
            expanded_path = os.path.expandvars(app_path)

            if app_path.endswith(".exe"):
                subprocess.Popen([expanded_path])
            else:
                subprocess.Popen([app_path])

            return f"Opening {app_name}, sir."
        except FileNotFoundError:
            return f"I could not find {app_name} on this system, sir."
        except Exception:
            return f"I was unable to open {app_name}, sir."
