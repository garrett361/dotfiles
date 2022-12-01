-- https://github.com/nvim-neorocks/nvim-best-practices?tab=readme-ov-file#speaking_head-user-commands

local scratch_dir = vim.fn.stdpath("data") .. "/scratch/"

local open_scratch = function()
	local fzf = require("fzf-lua")

	local files = vim.fn.glob(scratch_dir .. "*", false, true)

	fzf.fzf_exec(files, {
		prompt = "Saved Scratch Files | <c-r>: remove >",
		previewer = "builtin",
		fzf_opts = { ["--multi"] = true },
		actions = {
			["default"] = function(selected)
				if #selected > 0 then
					local filepath = selected[1]
					vim.cmd("edit " .. filepath)
				end
			end,
			["ctrl-r"] = function(selected)
				for _, s in ipairs(selected) do
					local filepath = s
					os.remove(filepath)
					-- Refresh the picker
				end
			end,
		},
	})
end

vim.api.nvim_create_user_command("Scratch", function(opts)
	local file = opts.args
	if file == "" then
		open_scratch()
	else
		vim.cmd("edit " .. scratch_dir .. file)
	end
end, {
	nargs = "*",
	desc = "Create or edit scratch file.",
	complete = function(_)
		local files = require("nvim_utils.os").get_files_in_directory(scratch_dir)
		return files
	end,
})
