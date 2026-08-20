local prequire = require("nvim_utils").prequire

prequire("user.keymaps") -- Must be loaded before lazy
prequire("user.options")
prequire("user.autocommands")
prequire("user.user_commands")

-- Only load plugins when not in vscode
if not vim.g.vscode then
	-- lazy pins itself in lazy-lock.json but never restores itself: its install pipeline skips
	-- plugins already on disk, so the bootstrap clone below survives untouched and the next
	-- lockfile write records it over the pinned entry. Pin it here instead, before lazy loads.
	-- Every failure is soft, since the stable clone is a working fallback.
	local function checkout_pinned_lazy(lazypath)
		local f = io.open(vim.fn.stdpath("config") .. "/lazy-lock.json", "r")
		if not f then
			return
		end
		local ok, lock = pcall(vim.json.decode, f:read("*a"))
		f:close()
		local entry = ok and type(lock) == "table" and lock["lazy.nvim"]
		local commit = type(entry) == "table" and entry.commit
		if type(commit) ~= "string" then
			return
		end
		vim.fn.system({ "git", "-C", lazypath, "checkout", "--quiet", commit })
		if vim.v.shell_error ~= 0 then
			vim.notify("lazy.nvim: cannot check out pinned " .. commit, vim.log.levels.WARN)
		end
	end

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
			-- getchar never returns under --headless, which install.sh relies on.
			if #vim.api.nvim_list_uis() > 0 then
				vim.fn.getchar()
			end
			os.exit(1)
		end
		checkout_pinned_lazy(lazypath)
	end
	vim.opt.rtp:prepend(lazypath)

	local lazy = prequire("lazy")

	-- Install your plugins here
	lazy.setup("plugins", opts) -- Loads files from under the plugins/ dir
end
