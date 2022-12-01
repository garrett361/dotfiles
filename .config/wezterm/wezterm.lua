local wezterm = require("wezterm")

local config = wezterm.config_builder()

config.font = wezterm.font("JetBrainsMono Nerd Font")
config.font_size = 14
config.max_fps = 201

-- config.enable_tab_bar = false
config.hide_tab_bar_if_only_one_tab = true
config.window_decorations = "RESIZE"
config.enable_kitty_graphics = true
config.warn_about_missing_glyphs = false

return config
