local M = {}

local py_root_files = { "pyproject.toml", "pyrightconfig.json", ".git" }

M.basedpyright = function()
	vim.lsp.start({
		name = "basedpyright",
		cmd = { "basedpyright-langserver", "--stdio" },
		root_dir = vim.fs.root(0, py_root_files),
		settings = {
			basedpyright = {
				analysis = {
					autoSearchPaths = true,
					useLibraryCodeForTypes = true,
					diagnosticMode = "openFilesOnly",
					disableOrganizeImports = true,
					typeCheckingMode = "off",
				},
			},
		},
	})
end

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
