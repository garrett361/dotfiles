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
		type = "python",
		request = "launch",
		name = "torchrun",
		program = function()
			local torchrun_path = vim.fn.exepath("torchrun")
			if torchrun_path == "" then
				error("torchrun not found in PATH. Ensure PyTorch is installed.")
			end
			return torchrun_path
		end,
		args = function()
			-- Calculate default number of processes based on CUDA_VISIBLE_DEVICES
			local default_nproc = "2"
			local cuda_devices = os.getenv("CUDA_VISIBLE_DEVICES")
			if cuda_devices and cuda_devices ~= "" then
				local gpu_count = 0
				for _ in cuda_devices:gmatch("[^,]+") do
					gpu_count = gpu_count + 1
				end
				default_nproc = tostring(gpu_count)
			end

			local nproc = vim.fn.input("Number of processes (default " .. default_nproc .. "): ")
			if nproc == "" then
				nproc = default_nproc
			end
			local script = vim.fn.expand("%:p")
			local script_args = vim.fn.input("Script arguments (" .. script .. "): ")

            local port = math.random(29501, 29600)
			local args = {
				"--nproc_per_node=" .. nproc,
				"--master_port=" .. port,
				script,
			}

			if script_args ~= "" then
				for arg in script_args:gmatch("%S+") do
					table.insert(args, arg)
				end
			end

			return args
		end,
		cwd = "${workspaceFolder}",
		console = "integratedTerminal",
		justMyCode = false,
		subProcess = true,
		-- Automatically stop at entry point
		stopOnEntry = false,
	})
	-- Use pytest by default
	nvim_dap_python.test_runner = "pytest_pdb"
end
return M
