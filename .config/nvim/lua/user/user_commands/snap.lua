-- Code snapshots: https://www.justinrassier.com/blog/posts/2024-04-17-how-to-make-a-code-snapshot-plugin-in-neovim
vim.api.nvim_create_user_command("Snap", function()
	-- snag the file type from the buffer
	local file_type = vim.bo.filetype

	-- get the text from the visual selection as a table
	local text = vim.fn.getline(vim.fn.getpos("'<")[2], vim.fn.getpos("'>")[2])

	-- join it together into one string
	local full_text = table.concat(text, "\n")

	-- write the file to /tmp/freeze...probably could find a better place to put this so it's
	-- cross platform, but it works for me ¯\_(ツ)_/¯
	local file_path = "/tmp/freeze"
	local file = io.open(file_path, "w")
	if file == nil then
		print("could not open file")
		return
	end
	file:write(full_text)
	file:close()

	-- call the freeze command with the file type we grabbed earlier
	local freeze_out = vim.fn.system(
		"freeze /tmp/freeze -l"
			.. file_type
			.. " -o /tmp/freeze.png --padding='0,0,-15,0' --theme github-dark"
	)
	vim.notify(freeze_out, vim.log.levels.INFO)

	--  This is the tricky bit. Use apple script to copy the image to the clipboard
	vim.fn.system(
		"osascript -e 'set the clipboard to (read (POSIX file \"/tmp/freeze.png\") as TIFF picture)'"
	)

	-- Delete the file
	-- os.remove(file_path)

	-- notify the user that the image has been copied to the clipboard
	vim.notify("Image copied to clipboard", vim.log.levels.INFO)
end, {
	-- make sure the command is only available in visual mode
	range = true,
})
