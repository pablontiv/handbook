package contracts

type OperatorObservation struct {
	Schema        SchemaID `json:"schema"`
	ObservationID string   `json:"observation_id"`
	Runtime       string   `json:"runtime"`
	Challenge     string   `json:"challenge"`
	Declaration   string   `json:"declaration"`
	Freshness     string   `json:"freshness"`
}
