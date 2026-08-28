package contracts

import "testing"

func TestSHA256Hex(t *testing.T) {
	got := SHA256([]byte("abc"))
	want := SHA256Hex("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
	if got != want {
		t.Fatalf("SHA256 = %s, want %s", got, want)
	}
}

func TestPayloadDigestUsesPayloadOnly(t *testing.T) {
	payload := MinimalPlanPayloadForTest()
	got, err := PayloadDigest(payload)
	if err != nil {
		t.Fatalf("PayloadDigest() error = %v", err)
	}
	payloadBytes, err := CanonicalBytes(payload)
	if err != nil {
		t.Fatalf("CanonicalBytes(payload) error = %v", err)
	}
	want := SHA256(payloadBytes)
	if got != want {
		t.Fatalf("PayloadDigest = %s, want payload SHA256 %s", got, want)
	}
	envelope := PlanEnvelope{Schema: SchemaPlan, ApprovalDigest: got, Payload: payload}
	envelopeBytes, err := CanonicalBytes(envelope)
	if err != nil {
		t.Fatalf("CanonicalBytes(envelope) error = %v", err)
	}
	if got == SHA256(envelopeBytes) {
		t.Fatalf("PayloadDigest must not be computed over the plan envelope")
	}
	if _, err := VerifyPlanEnvelope(envelopeBytes, got); err != nil {
		t.Fatalf("VerifyPlanEnvelope() error = %v", err)
	}
}

func TestVerifyPlanEnvelopeRejectsApprovalMismatch(t *testing.T) {
	payload := MinimalPlanPayloadForTest()
	digest, err := PayloadDigest(payload)
	if err != nil {
		t.Fatal(err)
	}
	envelopeBytes, err := CanonicalBytes(PlanEnvelope{Schema: SchemaPlan, ApprovalDigest: digest, Payload: payload})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := VerifyPlanEnvelope(envelopeBytes, SHA256Hex("0000000000000000000000000000000000000000000000000000000000000000")); err == nil {
		t.Fatalf("VerifyPlanEnvelope() succeeded with wrong approved digest")
	}
}
