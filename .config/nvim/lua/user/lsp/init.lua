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
	root_markers = {
		".luarc.json",
		".luarc.jsonc",
		".stylua.toml",
		"stylua.toml",
		"selene.toml",
		"selene.yml",
		".git",
	},
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
	root_markers = {
		".clangd",
		".clang-tidy",
		".clang-format",
		"compile_commands.json",
		"compile_flags.txt",
		"configure.ac",
		".git",
	},
	capabilities = capabilities,
	on_attach = function(client, bufnr)
		setup_inlay_hints(client, bufnr)
		-- Formatting is left enabled here, unlike ruff: clangd embeds clang-format and reads
		-- the same .clang-format, so conform routes c/cpp/cuda through it rather than a
		-- standalone binary that would be a second copy of the same tool.
		-- For handling https://github.com/neovim/neovim/pull/16694#issuecomment-996947306
		client.server_capabilities.offsetEncoding = { "utf-16" }
	end,
}

vim.lsp.config.ruff = {
	cmd = { "ruff", "server" },
	root_markers = { "pyproject.toml", "ruff.toml", ".ruff.toml", ".git" },
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
	root_markers = { "pyproject.toml", "ty.toml", ".ty.toml", ".git" },
	capabilities = capabilities,
	on_attach = function(client, bufnr)
		setup_inlay_hints(client, bufnr)
	end,
}

vim.lsp.config.tinymist = {
	cmd = { "tinymist" },
	root_markers = { ".git" },
	capabilities = capabilities,
	settings = {
		projectResolution = "lockedDatabase",
		exportPdf = "onSave",
		semanticTokens = "disable",
	},
	-- https://github.com/neovim/neovim/issues/30675#issuecomment-2395272151
	offset_encoding = "utf-8",
}

-- Auto-call vim.lsp.enable for all mason-installed lsps. stylua is excluded because it is
-- installed here as a conform formatter, but lspconfig also ships a `stylua --lsp` server and
-- mason-lspconfig maps the package to it, so every lua buffer would start a second, useless
-- client (conform never asks the LSP to format).
local mason_lspconfig = require("nvim_utils").prequire("mason-lspconfig")
mason_lspconfig.setup({
	-- clangd is the one server worth installing unprompted: it is a hard requirement for C and
	-- C++ LSP, and it also formats those buffers via conform. Mason owns it on macOS too, so the
	-- version stops tracking whatever Xcode ships. It has no aarch64 Linux build, so those
	-- machines log a Mason error each launch and get no C/C++ support either way.
	ensure_installed = { "clangd" },
	automatic_enable = { exclude = { "stylua" } },
})

-- automatic_enable already covers clangd once Mason installs it. Enabling it explicitly is the
-- fallback for machines where that install cannot succeed or has not run yet, and for a system
-- clangd already on PATH.
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
