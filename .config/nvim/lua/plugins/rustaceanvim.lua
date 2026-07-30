-- rustaceanvim is configured through vim.g, not setup(), and the value has to be in place before
-- its ftplugin runs.
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
