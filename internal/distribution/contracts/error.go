package contracts

type PublicError struct {
	Schema   SchemaID      `json:"schema"`
	Code     string        `json:"code"`
	Message  string        `json:"message"`
	Exit     int           `json:"exit"`
	Command  string        `json:"command"`
	Evidence []EvidenceRef `json:"evidence"`
}
