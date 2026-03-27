package atbms

default allow = false
default effect = "BLOCK"
default reason = "Denied by default"
default rule_id = "default_deny"

allow {
  tool_in_manifest
  not constraint_violated
}

effect = "ALLOW" {
  allow
}

reason = "Tool allowed by manifest" {
  allow
}

rule_id = "allow_manifest" {
  allow
}

tool_in_manifest {
  input.tool_name == input.tool_manifest[_]
}

constraint_violated {
  input.tool_name == "bash_exec"
  input.agent_tags[_] == "untrusted"
}

constraint_violated {
  input.tool_name == "read_file"
  path := input.args.path
  not startswith(path, "/workspace/")
  not startswith(path, "/tmp/")
}

effect = "REQUIRE_APPROVAL" {
  input.tool_name == "http_request"
  not trusted_domain
}

reason = "Outbound HTTP requires approval" {
  input.tool_name == "http_request"
  not trusted_domain
}

rule_id = "require_approval_http" {
  input.tool_name == "http_request"
  not trusted_domain
}

trusted_domain {
  startswith(input.args.url, "https://api.example.com")
}
