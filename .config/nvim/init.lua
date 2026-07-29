local prequire = require("nvim_utils").prequire

prequire("user.keymaps") -- Must be loaded before lazy
prequire("user.options")
prequire("user.autocommands")
prequire("user.user_commands")

-- Only load plugins when not in vscode
if not vim.g.vscode then
	-- Installing lazy
	local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"
	if not vim.uv.fs_stat(lazypath) then
		local out = vim.fn.system({
			"git",
			"clone",
			"--filter=blob:none",
			"https://github.com/folke/lazy.nvim.git",
			"--branch=stable", -- latest stable release
			lazypath,
		})
		if vim.v.shell_error ~= 0 then
			vim.api.nvim_echo({
				{ "Failed to clone lazy.nvim:\n", "ErrorMsg" },
				{ out, "WarningMsg" },
				{ "\nPress any key to exit" },
			}, true, {})
			vim.fn.getchar()
			os.exit(1)
		end
	end
	vim.opt.rtp:prepend(lazypath)

	local lazy = prequire("lazy")

	-- Install your plugins here
	lazy.setup("plugins", opts) -- Loads files from under the plugins/ dir
end
