local function get_visible_cuda_devices()
	local devices = os.getenv("CUDA_VISIBLE_DEVICES")
	if not devices or devices == "" then
		return nil
	end
	return #(devices:gsub("[^,]", "")) + 1
end

return {
	name = "torchrun",
	builder = function()
		local default_sh_full_path = vim.fn.expand("%:p")
		local cmd = { "torchrun", "--nproc-per-node" }

		local num_gpus = get_visible_cuda_devices()
		local default_world_size = num_gpus or 2
		local world_size =
			vim.fn.input("\n\nWORLD_SIZE (default " .. tostring(default_world_size) .. "):")
		if world_size == "" then
			world_size = tostring(default_world_size)
		end

		table.insert(cmd, world_size)
		table.insert(cmd, default_sh_full_path)

		local extra_args = vim.fn.input("\n\nCMD:" .. table.concat(cmd, " ") .. "\n\nArgs: ")
		if extra_args ~= "" then
			for a in extra_args:gmatch("%S+") do
				table.insert(cmd, a)
			end
		end

		return {
			cmd = cmd,
			args = {},
			components = { "default" },
		}
	end,
	condition = {
		filetype = { "python" },
	},
	priority = 2,
}
