workflow "Pull Request into Review Pipeline" {
  on = "pull_request"
  resolves = ["HTTP client"]
}

action "HTTP client" {
  uses = "swinton/httpie.action@02571a073b9aaf33930a18e697278d589a8051c1"
  secrets = ["ZENHUB_KEY"]
  env = {
    REPO_ID = "jq .pull_request.head.repo.id $HOME/$GITHUB_ACTION.response.body",
    ISSUE_NUMBER = "jq .number $HOME/$GITHUB_ACTION.response.body",
    DESTINATION_PIPELINE="5bfed342b82313279e75374e",
    DESTINATION_POSITION="top",
  },
  args = [
  "POST", "api.zenhub.io/p1/respositories/`$REPO_ID`/issus/`$ISSUE_NUMBER`/moves", "X-Authentication-Token:$ZENHUIB_TOKEN",
  "pipeline_id=$DESTINATION_PIPELINE", "position=$DESTINATION_POSITION"]
}
