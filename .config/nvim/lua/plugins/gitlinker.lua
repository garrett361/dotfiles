local exec = require("nvim_utils.exec")
local prequire = require("nvim_utils").prequire
local function config()
	local gitlinker = prequire("gitlinker")
	gitlinker.setup({
		router = {
			browse = {
				["^github%.ibm%.com"] = require("gitlinker.routers").github_browse,
			},
			blame = {
				["^github%.ibm%.com"] = require("gitlinker.routers").github_blame,
			},
		},
	})
end

---Returns the text immediately preceding the first "/". E.g. "fsfsd sfs/sdsfs" returns "sfs".
---@param str string
---@return string
local function get_text_before_first_slash(str)
	for word in str:gmatch("%S+") do
		local idx = word:find("/")
		if idx then
			return word:sub(1, idx - 1)
		end
	end
	return ""
end

return {
	"linrongbin16/gitlinker.nvim",
	cmd = "GitLink",
	config = config,
	lazy = true,
	keys = {
		{
			"<leader>ay",
			function()
				local commit_hash = exec.shell("git rev-parse HEAD")
				-- Gives link to the first remote listed in the below command.
				local remote = get_text_before_first_slash(
					exec.shell("git branch -r --contains " .. commit_hash)
				)
				prequire("gitlinker").link({ remote = remote })
			end,
			mode = { "n", "v" },
		},
	},
}
