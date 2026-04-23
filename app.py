from flask import Flask, render_template, request
import pandas as pd

app = Flask(__name__)

LEAGUE_AVG_3P = 0.36
STAT_LABELS = {
    "points_per_game": "Points Per Game",
    "assists_per_game": "Assists Per Game",
    "rebounds_per_game": "Rebounds Per Game",
    "games_played": "Games Played",
    "fg_pct": "Field Goal %",
    "three_pt_shooting": "3PT Shooting",
    "turnovers_per_game": "Turnovers Per Game",
    "steals_per_game": "Steals Per Game",
    "blocks_per_game": "Blocks Per Game",
}
COMPARISON_STATS = [
    "points_per_game",
    "assists_per_game",
    "rebounds_per_game",
    "games_played",
    "fg_pct",
    "fg3_pct",
    "three_pa",
    "three_pt_shooting",
    "turnovers_per_game",
    "steals_per_game",
    "blocks_per_game",
]

# Load your cleaned data once
df = pd.read_json("new_stats.json")

# Stats where LOWER is better
negative_stats = {"turnovers_per_game"}
ranking_stats = [
    "points_per_game",
    "assists_per_game",
    "rebounds_per_game",
    "games_played",
    "fg_pct",
    "three_pt_shooting",
    "turnovers_per_game",
    "steals_per_game",
    "blocks_per_game",
]


def prepare_player_data(dataframe):
    cleaned_df = dataframe.copy()

    numeric_column_map = {
        "points_per_game": "PTS",
        "assists_per_game": "AST",
        "rebounds_per_game": "TRB",
        "games_played": "G",
        "fg_pct": "FG%",
        "fg3_pct": "3P%",
        "three_pa": "3PA",
        "turnovers_per_game": "TOV",
        "steals_per_game": "STL",
        "blocks_per_game": "BLK",
    }

    for new_col, original_col in numeric_column_map.items():
        cleaned_df[new_col] = pd.to_numeric(cleaned_df[original_col], errors="coerce")

    cleaned_df["player_name"] = cleaned_df["Player"]
    cleaned_df["team"] = cleaned_df["Team"]
    cleaned_df["position"] = cleaned_df["Pos"]

    league_average_rows = cleaned_df[cleaned_df["player_name"].eq("League Average")]
    league_avg_3p = LEAGUE_AVG_3P
    if not league_average_rows.empty and pd.notna(league_average_rows["fg3_pct"].iloc[0]):
        league_avg_3p = league_average_rows["fg3_pct"].iloc[0]

    cleaned_df["fg3_pct"] = cleaned_df["fg3_pct"].fillna(0)
    cleaned_df["three_pa"] = cleaned_df["three_pa"].fillna(0)
    cleaned_df["three_pt_shooting"] = (
        (cleaned_df["fg3_pct"] - league_avg_3p) * cleaned_df["three_pa"]
    )

    return cleaned_df[
        cleaned_df["player_name"].ne("League Average")
        & cleaned_df["team"].notna()
        & cleaned_df["position"].notna()
        & cleaned_df[ranking_stats].notna().all(axis=1)
    ].copy()


df = prepare_player_data(df)


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
    table_columns = [
        "Rank", "Position", "Player", "Team", "Score", "PPG", "APG", "RPG",
        "SPG", "BPG", "Games", "FG%", "3P%", "3PA", "TOV"
    ]
    comparison_players = df.sort_values("player_name")[[
        "player_name",
        "team",
        "position",
        *COMPARISON_STATS,
    ]].to_dict(orient="records")

    default_weights = {
        "points_per_game": 40,
        "assists_per_game": 20,
        "rebounds_per_game": 15,
        "games_played": 15,
        "fg_pct": 10,
        "three_pt_shooting": 10,
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

        visible_rankings = pd.DataFrame({
            "Rank": ranked_df["rank"],
            "Position": ranked_df["position"],
            "Player": ranked_df["player_name"],
            "Team": ranked_df["team"],
            "Score": ranked_df["ranking_score"],
            "PPG": ranked_df["points_per_game"],
            "APG": ranked_df["assists_per_game"],
            "RPG": ranked_df["rebounds_per_game"],
            "SPG": ranked_df["steals_per_game"],
            "BPG": ranked_df["blocks_per_game"],
            "Games": ranked_df["games_played"],
            "FG%": ranked_df["fg_pct"],
            "3P%": ranked_df["fg3_pct"],
            "3PA": ranked_df["three_pa"],
            "TOV": ranked_df["turnovers_per_game"],
        }).head(750)
        rankings = []

        for original_row, display_row in zip(ranked_df.head(750).to_dict(orient="records"), visible_rankings.to_dict(orient="records")):
            score_breakdown = []
            for stat in ranking_stats:
                contribution_value = round(float(original_row.get(f"{stat}_contribution", 0)), 3)
                score_breakdown.append({
                    "label": STAT_LABELS[stat],
                    "value": contribution_value,
                })

            rankings.append({
                **display_row,
                "_player_name": display_row["Player"],
                "_score_total": round(float(original_row["ranking_score"]), 3),
                "_score_breakdown": score_breakdown,
            })

        default_weights = weights

    return render_template(
        "index.html",
        rankings=rankings,
        weights=default_weights,
        table_columns=table_columns,
        comparison_players=comparison_players,
        comparison_stat_labels={**STAT_LABELS, "fg3_pct": "3P%", "three_pa": "3PA"},
        comparison_stat_order=COMPARISON_STATS,
    )


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=8000)
