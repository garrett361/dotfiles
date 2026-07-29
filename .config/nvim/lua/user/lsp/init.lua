local settings = {
	ui = {
		border = "none",
		icons = {
			package_installed = "◍",
			package_pending = "◍",
			package_uninstalled = "◍",
		},
	},
	log_level = vim.log.levels.INFO,
	max_concurrent_installers = 4,
}

local mason = require("nvim_utils").prequire("mason")
mason.setup(settings)

local capabilities = vim.lsp.protocol.make_client_capabilities()
capabilities.textDocument.completion.completionItem.snippetSupport = true

-- cmp
local cmp_nvim_lsp = require("nvim_utils").prequire("cmp_nvim_lsp")
capabilities = cmp_nvim_lsp.default_capabilities(capabilities)

local function setup_inlay_hints(client, bufnr)
	if client.server_capabilities.inlayHintProvider then
		vim.g.inlay_hints_visible = true
		vim.lsp.inlay_hint.enable(true, { bufnr = bufnr })
	end
end

vim.lsp.config.lua_ls = {
	cmd = { "lua-language-server" },
	root_dir = vim.fs.root(0, {
		".luarc.json",
		".luarc.jsonc",
		".stylua.toml",
		"stylua.toml",
		"selene.toml",
		"selene.yml",
		".git",
	}),
	capabilities = capabilities,
	settings = { Lua = { workspace = { checkThirdParty = false } } },
	on_init = function(client)
		if client.workspace_folders then
			local path = client.workspace_folders[1].name
			if
				vim.uv.fs_stat(path .. "/.luarc.json")
				or vim.uv.fs_stat(path .. "/.luarc.jsonc")
			then
				return
			end
		end

		client.config.settings.Lua = vim.tbl_deep_extend("force", client.config.settings.Lua, {
			runtime = {
				-- Tell the language server which version of Lua you're using
				-- (most likely LuaJIT in the case of Neovim)
				version = "LuaJIT",
			},
			-- Make the server aware of Neovim runtime files
			workspace = {
				checkThirdParty = false,
				library = {
					vim.env.VIMRUNTIME,
					-- Depending on the usage, you might want to add additional paths here.
					-- "${3rd}/luv/library"
					-- "${3rd}/busted/library",
				},
				-- or pull in all of 'runtimepath'. NOTE: this is a lot slower and will cause issues when working on your own configuration (see https://github.com/neovim/nvim-lspconfig/issues/3189)
				-- library = vim.api.nvim_get_runtime_file("", true)
			},
		})
	end,
}

vim.lsp.config.clangd = {
	cmd = { "clangd" },
	root_dir = vim.fs.root(0, {
		".clangd",
		".clang-tidy",
		".clang-format",
		"compile_commands.json",
		"compile_flags.txt",
		"configure.ac",
		".git",
	}),
	capabilities = capabilities,
	on_attach = function(client, bufnr)
		setup_inlay_hints(client, bufnr)
		client.server_capabilities.documentFormattingProvider = false
		-- For handling https://github.com/neovim/neovim/pull/16694#issuecomment-996947306
		client.server_capabilities.offsetEncoding = { "utf-16" }
	end,
}

vim.lsp.config.ruff = {
	cmd = { "ruff", "server" },
	root_dir = vim.fs.root(0, { "pyproject.toml", "ruff.toml", ".ruff.toml", ".git" }),
	capabilities = capabilities,
	init_options = {
		settings = {
			lint = {
				extendSelect = {
					"A",
					"ARG",
					"B",
					"C4",
					"C90",
					"FURB",
					"INT",
					"N",
					"NPY",
					"PD",
					"PERF",
					"PIE",
					"PT",
					"PYI",
					"Q",
					"RET",
					"RSE",
					"RUF",
					"SIM",
					"TRY",
					"UP",
				},
				ignore = { "RET504", "N803", "N806", "TRY003" },
			},
		},
	},
	on_attach = function(client, bufnr)
		setup_inlay_hints(client, bufnr)
		client.server_capabilities.hoverProvider = false
		client.server_capabilities.documentFormattingProvider = false
	end,
}

vim.lsp.config.ty = {
	cmd = { "ty", "server" },
	filetypes = { "python" },
	root_dir = vim.fs.root(0, { "pyproject.toml", "ty.toml", ".ty.toml", ".git" }),
	capabilities = capabilities,
	on_attach = function(client, bufnr)
		setup_inlay_hints(client, bufnr)
	end,
}

vim.lsp.config.tinymist = {
	cmd = { "tinymist" },
	root_dir = vim.fs.root(0, { ".git" }),
	capabilities = capabilities,
	settings = {
		projectResolution = "lockedDatabase",
		exportPdf = "onSave",
		semanticTokens = "disable",
	},
	-- https://github.com/neovim/neovim/issues/30675#issuecomment-2395272151
	offset_encoding = "utf-8",
}

-- Auto-call vim.lsp.enable for all mason-installed lsps
local mason_lspconfig = require("nvim_utils").prequire("mason-lspconfig")
mason_lspconfig.setup()

-- clangd is not a mason package, so it needs enabling by hand; mason-lspconfig only
-- auto-enables what it installed.
vim.lsp.enable({ "clangd", "ruff", "ty" })

-- Configuring signs and other visuals

vim.diagnostic.config({
	virtual_text = true, -- virtual text
	-- nvim 0.12 ignores sign_define() for diagnostics; sign text comes from here now.
	signs = {
		text = {
			[vim.diagnostic.severity.ERROR] = "",
			[vim.diagnostic.severity.WARN] = "",
			[vim.diagnostic.severity.HINT] = "󰰂",
			[vim.diagnostic.severity.INFO] = "",
		},
	},
	update_in_insert = true,
	underline = false,
	severity_sort = true,
	float = {
		focusable = true,
		style = "minimal",
		border = "rounded",
		source = true,
		header = "",
		prefix = "",
	},
})

-- Replaces the vim.lsp.with + vim.lsp.handlers overrides for hover and signatureHelp, both
-- deprecated for removal in 0.13. Note this borders every float, not just those two.
vim.o.winborder = "rounded"
