vim.o.sessionoptions = "blank,buffers,curdir,folds,help,tabpages,winsize,winpos,localoptions"
local function config()
	local auto_session = require("nvim_utils").prequire("auto-session")
	auto_session.setup({
		log_level = "info",
		auto_session_enable_last_session = false,
		auto_session_root_dir = vim.fn.stdpath("data") .. "/sessions/",
		auto_session_enabled = true,
		auto_save_enabled = true,
		auto_restore_enabled = true,
		auto_session_suppress_dirs = nil,
		auto_session_use_git_branch = true,
		-- the configs below are lua only
		bypass_session_save_file_types = nil,
		session_lens = { load_on_setup = false },
	})
end
return {
	"rmagatti/auto-session",
	config = config,
}
