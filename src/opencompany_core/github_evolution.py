"""Typed result for owner-approved GitHub code-evolution proposals."""
from dataclasses import dataclass

@dataclass(frozen=True)
class GitHubPullRequest:
    number: int
    url: str
    branch: str
    commit_sha: str
    title: str
    def __post_init__(self):
        if self.number < 1 or not all((self.url,self.branch,self.commit_sha,self.title)):
            raise ValueError("invalid GitHub pull request metadata")
