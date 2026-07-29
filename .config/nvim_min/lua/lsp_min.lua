local M = {}

local py_root_files = { "pyproject.toml", "pyrightconfig.json", ".git" }

M.pylsp = function()
	vim.lsp.start({
		name = "pylsp",
		cmd = { "pylsp" },
		root_dir = vim.fs.root(0, py_root_files),
		settings = {
			pylsp = {
				plugins = {
					flake8 = { enabled = false },
					pycodestyle = { enabled = false },
					pyflakes = { enabled = false },
				},
			},
		},
	})
end

return M
