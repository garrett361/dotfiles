local function config()
	local nvim_lsp_endhints = require("nvim_utils").prequire("lsp-endhints")
	nvim_lsp_endhints.setup({
		icons = {
			type = " ",
			parameter = " ",
			offspec = " ", -- hint kind not defined in official LSP spec
			unknown = " ", -- hint kind is nil
		},
		autoEnableHints = false,
	})
end
return { "chrisgrieser/nvim-lsp-endhints", event = "LspAttach", opts = {}, config = config }
