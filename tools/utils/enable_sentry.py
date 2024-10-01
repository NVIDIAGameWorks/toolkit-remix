SETTINGS_FILE = "source/apps/lightspeed.app.trex.app.settings.toml"
DISABLED_TEXT = "enableSentry = false"
ENABLED_TEXT = "enableSentry = true"

with open(SETTINGS_FILE, "r") as ff:
    orig_text = ff.read()

new_text = orig_text.replace(DISABLED_TEXT, ENABLED_TEXT)
with open(SETTINGS_FILE, "w") as ff:
    ff.write(new_text)
