import pytest

from app.negotiation.agreements import AgreementStore, AllocationProposal, CommitError
from app.validation.validator import ValidationResult


def ok():
    return ValidationResult(True, False, [], [], 100, 200, {}, 0)


def prop(version=0):
    return AllocationProposal({"hospital_agent": 100}, version, "test", 200, 200, 0)


def test_commit_increments_version_and_is_idempotent():
    s = AgreementStore()
    p = prop()
    a, new = s.commit(p, ok(), "t", 1)
    assert new and a.version == 1 and s.version == 1
    a2, new2 = s.commit(p, ok(), "t", 1)
    assert not new2 and a2.version == 1 and s.version == 1


def test_stale_proposal_rejected():
    s = AgreementStore()
    s.commit(prop(0), ok(), "t", 1)
    with pytest.raises(CommitError) as e:
        s.commit(prop(0), ok(), "t", 2)
    assert e.value.code == "STALE_PROPOSAL"


def test_invalid_never_commits():
    s = AgreementStore()
    bad = ValidationResult(False, False, [], [], 0, 0, {}, 0)
    with pytest.raises(CommitError):
        s.commit(prop(0), bad, "t", 1)
    assert s.version == 0 and s.current is None
