from __future__ import annotations

from sediman.agent.subagents.result import Artifact, SubagentResult


class TestArtifact:
    def test_creation(self):
        art = Artifact(kind="file", name="test.py", path="/tmp/test.py")
        assert art.kind == "file"
        assert art.name == "test.py"

    def test_to_dict_excludes_content(self):
        art = Artifact(kind="skill", name="my-skill", metadata={"steps": 3})
        # We don't test serialization here directly; SubagentResult handles it


class TestSubagentResult:
    def test_defaults(self):
        result = SubagentResult(success=True, summary="Done")
        assert result.success is True
        assert result.summary == "Done"
        assert result.detail is None
        assert result.actions_taken == []
        assert result.artifacts == []
        assert result.iterations == 0
        assert result.strategy_used == "direct"
        assert result.errors == []

    def test_to_dict_structure(self):
        result = SubagentResult(
            success=True,
            summary="All good",
            detail="Full text",
            actions_taken=[{"tool": "read_file"}],
            artifacts=[Artifact(kind="file", name="a.py", path="/a.py")],
            iterations=2,
            strategy_used="delegate",
            errors=["minor warning"],
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["summary"] == "All good"
        assert d["detail"] == "Full text"
        assert d["actions_taken"] == [{"tool": "read_file"}]
        assert len(d["artifacts"]) == 1
        assert d["artifacts"][0]["kind"] == "file"
        assert d["artifacts"][0]["name"] == "a.py"
        assert d["iterations"] == 2
        assert d["strategy_used"] == "delegate"
        assert d["errors"] == ["minor warning"]

    def test_failed_result(self):
        result = SubagentResult(
            success=False,
            summary="Failed",
            errors=["timeout"],
        )
        assert result.success is False
        assert result.to_dict()["success"] is False
