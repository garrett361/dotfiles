local M = {}
local prequire = require("nvim_utils").prequire

local function prune_trivial(items)
	return vim.tbl_filter(function(x)
		return type(x) == "string"
	end, items)
end

M.config = function()
	local nvim_dap = prequire("dap")
	local nvim_dap_utils = prequire("dap.utils")
	local nvim_dap_python = prequire("dap-python")

	-- Use the default pytest runner but with the additional --pdb flag.
	local test_runners = nvim_dap_python.test_runners
	test_runners.pytest_pdb = function(classname, methodname, opts)
		local path = vim.fn.expand("%:p")
		local test_name = prune_trivial({ path, classname, methodname })
		local test_path = table.concat(test_name, "::")
		-- -s "allow output to stdout of test"
		local args = { "-rfsP", "--pdb", "-s", test_path }
		return "pytest", args
	end

	local py_path = "python3"
	local mason_path = vim.fn.stdpath("data") .. "/mason/packages/debugpy/venv/bin/python3"
	if vim.fn.filereadable(mason_path) == "1" then
		py_path = mason_path
	end
	nvim_dap_python.setup(py_path)
	table.insert(nvim_dap.configurations.python, {
		type = "python",
		request = "launch",
		name = "Launch with args from cwd (justMyCode = false)",
		program = "${file}",
		cwd = "${workspaceFolder}",
		args = function()
			local args_string = vim.fn.input("Arguments: ")
			return nvim_dap_utils.splitstr(args_string)
		end,
		justMyCode = false,
		subProcess = true,
	})
	table.insert(nvim_dap.configurations.python, {
		type = "python",
		request = "launch",
		name = "PyTest",
		module = "pytest",
		cwd = "${workspaceFolder}",
		args = function()
			local args_string = vim.fn.input("Arguments: ")
			local arg_table = nvim_dap_utils.splitstr(args_string)
			table.insert(arg_table, 1, "${file}")
			return arg_table
		end,
		justMyCode = false,
		subProcess = true,
		console = "integratedTerminal",
	})
	table.insert(nvim_dap.configurations.python, {
		type = "python",
		request = "launch",
		name = "PyTest -- specify test, without leading ::",
		module = "pytest",
		cwd = "${workspaceFolder}",
		args = function()
			local args_string = vim.fn.input("Arguments: ")
			local arg_table = nvim_dap_utils.splitstr(args_string)
			arg_table[1] = "${file}" .. "::" .. arg_table[1]
			table.insert(arg_table, 1, "--pdb")
			return arg_table
		end,
		justMyCode = false,
		subProcess = true,
		console = "integratedTerminal",
	})
	table.insert(nvim_dap.configurations.python, {
	    type = 'python',
        request = 'launch',
        name = 'torchrun',
        program = vim.fn.exepath('torchrun'),
        args = function()
          local nproc = vim.fn.input('Number of processes (default 2): ')
          if nproc == '' then nproc = '2' end
          local script = vim.fn.expand('%:p')
          local script_args = vim.fn.input('Script arguments (' .. script ..'): ')

          local args = {
            '--nproc_per_node=' .. nproc,
            '--master_port=29501',
            script
          }

          if script_args ~= '' then
            for arg in script_args:gmatch('%S+') do
              table.insert(args, arg)
            end
          end

          return args
        end,
        cwd = '${workspaceFolder}',
        console = 'integratedTerminal',
        -- This tells DAP to debug the launched process directly
        subProcess = true,
        -- Automatically stop at entry point
        stopOnEntry = false,
    })
	-- Use pytest by default
	nvim_dap_python.test_runner = "pytest_pdb"
end
return M
