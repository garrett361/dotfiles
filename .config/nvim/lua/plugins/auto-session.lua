vim.o.sessionoptions = "blank,buffers,curdir,folds,help,tabpages,winsize,winpos,localoptions"
local function config()
	local auto_session = require("nvim_utils").prequire("auto-session")
	-- Everything else this used to pass was a deprecated alias whose value already
	-- matched the default, which also tripped auto-session's checkhealth warning.
	auto_session.setup({
		log_level = "info",
		git_use_branch_name = true,
		session_lens = { load_on_setup = false },
	})
end
return {
	"rmagatti/auto-session",
	config = config,
}
