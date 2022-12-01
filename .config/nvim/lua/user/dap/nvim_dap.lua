local M = {}
M.config = function()
	local dap = require("nvim_utils").prequire("dap")
	-- Signs and colors
	vim.cmd("hi DapBreakpoint guifg=#FF4040")
	vim.cmd("hi DapBreakpointCondition guifg=#FBB500")
	vim.cmd("hi DapStopped guifg=#FFF89C")
	vim.fn.sign_define(
		"DapBreakpoint",
		{ text = "󱥸", texthl = "DapBreakpoint", numhl = "DapBreakpoint" }
	)
	vim.fn.sign_define(
		"DapBreakpointCondition",
		{ text = "", texthl = "DapBreakpointCondition", numhl = "DapBreakpointCondition" }
	)
	vim.fn.sign_define("DapStopped", { text = "", texthl = "DapStopped", numhl = "DapStopped" })

	-- Clean printing (for python) https://github.com/mfussenegger/nvim-dap/pull/1089#issuecomment-1807038344
	-- Prefix dap command with . <cmd> for pretty printing
	dap.repl.commands.custom_commands = {
		["."] = function(text)
			local session = dap.session()
			if not session then
				vim.fn.input("Not in session")
				return
			end
			session:evaluate(text, function(err, resp)
				if err then
					dap.repl.append(err.message, nil, { newline = false })
				end
				if resp then
					dap.repl.append(resp.result, nil, { newline = false })
				end
			end)
		end,
		[".u"] = dap.up,
		[".d"] = dap.down,
		[".f"] = dap.focus_frame,
	}
end
return M
