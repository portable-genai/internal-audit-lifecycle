# The managed edge is authorized only when every primary adapter operation is real and covered by
# a live integration test. This is code-owned, not a caller override.
locals {
  managed_profile_implemented = false
}

check "managed_profile_is_implemented_before_serving" {
  assert {
    condition     = !var.production_edge_enabled || local.managed_profile_implemented
    error_message = "production_edge_enabled requires real, integration-tested managed adapter response mappings; see managed_readiness.py."
  }
}
