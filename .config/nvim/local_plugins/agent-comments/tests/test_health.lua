local health = require("agent-comments.health")

-- Externals are injected so the result does not depend on whether herdr happens to be
-- installed, or on whether the suite is run from inside a herdr session.
local function report(found, session_ok, reason)
	return health._report({
		executable = function()
			return found and 1 or 0
		end,
		available = function()
			return session_ok, reason
		end,
	})
end

T.test("health: a missing herdr CLI is an error", function()
	local out = report(false, true)
	T.eq(out[1][1], "error")
	T.ok(out[1][2]:find("PATH", 1, true), "the message names PATH")
	T.ok(out[1][3]:find("install herdr", 1, true), "the advice says to install herdr")
	T.eq(out[2][1], "ok")
	T.eq(out[2][3], nil, "an ok entry carries no advice")
end)

T.test("health: a missing session warns rather than errors, and carries the reason", function()
	local out = report(true, false, "not in a herdr session (HERDR_WORKSPACE_ID is unset)")
	T.eq(out[2][1], "warn")
	T.eq(out[2][2], "not in a herdr session (HERDR_WORKSPACE_ID is unset)")
	T.ok(out[2][3]:find("comments still work", 1, true), "the advice says commenting still works")
end)
