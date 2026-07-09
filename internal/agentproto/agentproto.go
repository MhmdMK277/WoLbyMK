// Package agentproto defines the wire protocol shared by the WoLmk desktop
// app and the WoLmk-Agent companion service. The transport is a single
// JSON request and a single JSON response over one TCP connection.
package agentproto

// DefaultPort is the TCP port the agent listens on unless overridden.
const DefaultPort = 9477

// Valid actions an agent understands.
const (
	ActionShutdown = "shutdown"
	ActionReboot   = "reboot"
	ActionSleep    = "sleep"
	ActionLock     = "lock"
	ActionPing     = "ping" // liveness check, no side effect
)

// Command is the request sent to the agent.
type Command struct {
	Action string `json:"action"`
	Token  string `json:"token"`
}

// Response is the agent's reply.
type Response struct {
	Status  string `json:"status"`            // "ok" or "error"
	Message string `json:"message,omitempty"` // set when Status is "error"
	Host    string `json:"host,omitempty"`    // agent hostname, on ping
}

// ValidAction reports whether action is one the agent can execute.
func ValidAction(action string) bool {
	switch action {
	case ActionShutdown, ActionReboot, ActionSleep, ActionLock, ActionPing:
		return true
	}
	return false
}
