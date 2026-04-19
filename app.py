from flask import Flask, render_template, request
import pandas as pd

app = Flask(__name__)

# Load your cleaned data once
df = pd.read_json("players_clean.json")

# Stats where LOWER is better
negative_stats = {"turnovers_per_game"}
ranking_stats = [
    "points_per_game",
    "assists_per_game",
    "rebounds_per_game",
    "games_played",
    "fg_pct",
    "fg3_pct",
    "turnovers_per_game",
    "steals_per_game",
    "blocks_per_game",
]


def clean_player_data(dataframe):
    cleaned_df = dataframe.copy()
    cleaned_df["fg3_pct"] = cleaned_df["fg3_pct"].fillna(0)

    return cleaned_df[
        cleaned_df["player_name"].ne("League Average")
        & cleaned_df["team"].notna()
        & cleaned_df["position"].notna()
        & cleaned_df[ranking_stats].notna().all(axis=1)
    ].copy()


df = clean_player_data(df)


def normalize_column(series, reverse=False):
    min_val = series.min()
    max_val = series.max()

    if max_val == min_val:
        return pd.Series([1.0] * len(series), index=series.index)

    normalized = (series - min_val) / (max_val - min_val)

    if reverse:
        normalized = 1 - normalized

    return normalized


def generate_rankings(dataframe, weights_dict):
    df = dataframe.copy()
    df["ranking_score"] = 0.0

    for stat, weight in weights_dict.items():
        if stat not in df.columns:
            raise ValueError(f"Column '{stat}' not found in dataset.")

        reverse = stat in negative_stats
        normalized_col = normalize_column(df[stat], reverse=reverse)

        contribution_col = f"{stat}_contribution"
        df[contribution_col] = normalized_col * weight
        df["ranking_score"] += df[contribution_col]

    df = df.sort_values(by="ranking_score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    df["ranking_score"] = df["ranking_score"].round(2)

    return df


@app.route("/", methods=["GET", "POST"])
def index():
    rankings = None

    default_weights = {
        "points_per_game": 40,
        "assists_per_game": 20,
        "rebounds_per_game": 15,
        "games_played": 15,
        "fg_pct": 10,
        "fg3_pct": 10,
        "turnovers_per_game": 10,
        "steals_per_game": 10,
        "blocks_per_game": 10,
    }

    if request.method == "POST":
        weights = {
            stat: float(request.form.get(stat, 0))
            for stat in ranking_stats
        }

        ranked_df = generate_rankings(df, weights)
        ranked_df = ranked_df.round(3)


        display_df = ranked_df.rename(columns={
            "rank": "Rank",
            "position": "Position",
            "player_name": "Player",
            "team": "Team",
            "ranking_score": "Score",
            "points_per_game": "PPG",
            "assists_per_game": "APG",
            "rebounds_per_game": "RPG",
            "games_played": "Games",
            "fg_pct": "FG%",
            "fg3_pct": "3P%",
            "turnovers_per_game": "TOV",
            "steals_per_game": "SPG",
            "blocks_per_game": "BPG"
        })

        rankings = display_df[
            ["Rank", "Position", "Player", "Team", "Score", "PPG", "APG", "RPG", "SPG", "BPG", "Games", "FG%", "3P%", "TOV"]
        ].head(750).to_dict(orient="records")

        default_weights = weights

    return render_template("index.html", rankings=rankings, weights=default_weights)


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=8000)
