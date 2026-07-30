-- rustaceanvim is configured through vim.g, not setup(), and the value has to be in place before
-- its ftplugin runs.
--
-- No capabilities here: rustaceanvim resolves vim.lsp.config("*") itself and merges it over this
-- table, so rust-analyzer picks up the blink.cmp completion capabilities. That resolution is a
-- rustaceanvim implementation detail and `version = "^9"` floats the minor, so if Rust completion
-- ever degrades to nvim's base capabilities, look here first.
local function init()
	vim.g.rustaceanvim = {
		-- nvim-dap-lldb already populates dap.configurations.rust with cargo-aware entries,
		-- which is what <A-d> uses. Without this, rustaceanvim appends a second set on attach
		-- and the picker shows both.
		dap = { autoload_configurations = false },
	}
end

return {
	"mrcjkb/rustaceanvim",
	-- v9 dropped nvim 0.11; ^8 was only the bridge while this config was still on it.
	version = "^9",
	lazy = false,
	init = init,
}
