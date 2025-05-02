-- Don't force install these to avoid unnecessary perf issues/installs on remote machines

local servers = {
	"basedpyright",
	"ruff",
}

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

-- Set up automatic server installation with mason-lspconfig
local lspconfig = require("nvim_utils").prequire("lspconfig")

local function setup_inlay_hints(client, bufnr)
	if client.server_capabilities.inlayHintProvider then
		vim.g.inlay_hints_visible = true
		vim.lsp.inlay_hint.enable(true, { bufnr = bufnr })
	end
end
local function handler(server)
	local opts = {
		capabilities = capabilities,
	}

	server = vim.split(server, "@")[1]

	-- Special options for particular servers
	if server == "pylsp" then
		-- For pylsp, ignore various complaints
		opts.settings = {
			pylsp = {
				plugins = {
					flake8 = { enabled = false },
					pycodestyle = { enabled = false },
					pyflakes = { enabled = false },
				},
			},
		}
	elseif server == "lua_ls" then
		opts.settings = { Lua = { workspace = { checkThirdParty = false } } }
		opts.on_init = function(client)
			if client.workspace_folders then
				local path = client.workspace_folders[1].name
				if
					vim.loop.fs_stat(path .. "/.luarc.json")
					or vim.loop.fs_stat(path .. "/.luarc.jsonc")
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
		end
	elseif server == "clangd" then
		opts.on_attach = function(client, bufnr)
			setup_inlay_hints(client, bufnr)
			client.server_capabilities.documentFormattingProvider = false
			-- For handling https://github.com/neovim/neovim/pull/16694#issuecomment-996947306
			client.server_capabilities.offsetEncoding = { "utf-16" }
		end
	elseif server == "ruff" then
		opts.init_options = {
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
		}
		opts.on_attach = function(client, bufnr)
			setup_inlay_hints(client, bufnr)
			client.server_capabilities.hoverProvider = false
			client.server_capabilities.documentFormattingProvider = false
		end
	elseif server == "pyright" then
		opts.on_attach = function(client, bufnr)
			setup_inlay_hints(client, bufnr)
			client.server_capabilities.hoverProvider = true
			client.server_capabilities.documentFormattingProvider = false
		end
		opts.settings = {
			python = {
				analysis = {
					autoSearchPaths = true,
					useLibraryCodeForTypes = true,
					diagnosticMode = "openFilesOnly",
					disableOrganizeImports = true,
					typeCheckingMode = "off",
				},
			},
		}
	elseif server == "basedpyright" then
		opts.on_attach = function(client, bufnr)
			setup_inlay_hints(client, bufnr)
			-- Favor diagnostics from ruff and avoid duplication.
			client.server_capabilities.diagnosticProvider = false
			client.server_capabilities.hoverProvider = true
			client.server_capabilities.typeCheckingMode = "off"
			client.server_capabilities.documentFormattingProvider = false
		end
		-- **Before using this, confirm that some `pyproject.toml`, `setup.py`, etc (see GH link)
		-- does not unexpectedly appear upstream of the dirs the LSP is jumping into.
		-- Use the below to only return vim's cwd as the root_dir. Useful if the lsp is facing OOMs
		-- and 100% CPU utilization. This has happened after go-to-def into other libraries,
		-- which places too-large dirs in the lsp's config.workspace_folders (inspect with
		-- :lua print(vim.inspect(vim.lsp.get_active_clients()))). For basedpyright, this can occur
		-- when one of the files in the below link is not in the library root, but instead in some
		-- upstream dir, leading to all of ~ being added into  workspace_folders.
		-- See https://github.com/neovim/nvim-lspconfig/blob/a9bc587e9ae0cbcb3e90a2e9342f86b3b78c4408/lua/lspconfig/server_configurations/basedpyright.lua#L3-L11
		-- opts.root_dir = function(fname)
		-- 	return vim.fn.getcwd()
		-- end
		opts.settings = {
			basedpyright = {
				analysis = {
					ignore = { "*" }, -- Disabled in favor of ruff.
					-- autoSearchPaths = true,
					-- useLibraryCodeForTypes = true,
					-- diagnosticMode = "openFilesOnly",
					-- disableOrganizeImports = true,
					-- typeCheckingMode = "off",
				},
			},
		}
	elseif server == "tinymist" then
		opts.settings = {
			projectResolution = "lockedDatabase",
			exportPdf = "onSave",
			semanticTokens = "disable",
		}
		-- https://github.com/neovim/neovim/issues/30675#issuecomment-2395272151
		opts.offset_encoding = "utf-8"
	end
	lspconfig[server].setup(opts)
end

local mason_lspconfig = require("nvim_utils").prequire("mason-lspconfig")

mason_lspconfig.setup({
	ensure_installed = servers,
	automatic_installation = true,
})

mason_lspconfig.setup_handlers({
	handler,
})

-- Configuring signs and other visuals

local signs = {

	{ name = "DiagnosticSignError", text = "" },
	{ name = "DiagnosticSignWarn", text = "" },
	{ name = "DiagnosticSignHint", text = "󰰂" },
	{ name = "DiagnosticSignInfo", text = "" },
}

for _, sign in ipairs(signs) do
	vim.fn.sign_define(sign.name, { texthl = sign.name, text = sign.text, numhl = "" })
end

local config = {
	virtual_text = true, -- virtual text
	signs = {
		active = signs, -- show signs
	},
	update_in_insert = true,
	underline = false,
	severity_sort = true,
	float = {
		focusable = true,
		style = "minimal",
		border = "rounded",
		source = "always",
		header = "",
		prefix = "",
	},
}

vim.diagnostic.config(config)

vim.lsp.handlers["textDocument/hover"] = vim.lsp.with(vim.lsp.handlers.hover, {
	border = "rounded",
})

vim.lsp.handlers["textDocument/signatureHelp"] = vim.lsp.with(vim.lsp.handlers.signature_help, {
	border = "rounded",
})
