## Evidence-Driven Development

For feature, bugfix, refactor, or test work:

- Load `evidence-driven-development` before brainstorming.
- Load it again after an approved design or plan and before test-driven development.
- Treat specifications, plans, documentation, mocks, fixtures, and existing code as claims rather than sufficient independent evidence.
- Do not treat a material `UNKNOWN` as fact or continue a dependent path until it is resolved or the path changes.

The Real-System Verification Gate below is EDD's strict live-system profile.

## Real-System Verification Gate

Before any deployment, mutation, migration, or test execution against a live or production-like external system:

1. **Verify the real contract first.** Query the actual target through read-only operations before designing or approving the mutating execution. Repeat representative reads enough to reveal unstable ordering, eventual consistency, optional fields, and shape variation.
2. **Derive tests from observed reality.** Build fixtures and acceptance cases from sanitized real responses and verified vendor behavior. Never treat fixtures invented from a specification, plan, reference implementation, or the code under test as sufficient evidence of the external contract.
3. **Treat specifications as claims, not facts.** Contrast every execution-critical assumption with the actual system. A plan, green unit suite, or internally consistent review does not authorize live execution when its external assumptions remain unverified.
4. **Record the evidence chain.** State which endpoints and samples were checked, what varied, what semantics were established, and how the tests encode those observations.
5. **Fail closed on unknowns.** If the real contract cannot be verified safely, mark it UNKNOWN, stop before mutation, and ask for the missing access or decision. Never guess, substitute an assumption, or proceed because the specification says it should work.
6. **Require a renewed gate after failure.** After any failed live attempt, do not retry mutation until the root cause is verified, reproduced by a failing test, fixed, independently reviewed, and explicitly reauthorized by the user.

Mandatory sequence: observe the real system read-only → verify semantics and variability → write a failing test from real evidence → implement minimally → validate locally → obtain explicit live authorization → mutate.
