import {
  BarChart,
  Callout,
  Card,
  CardBody,
  CardHeader,
  Grid,
  H1,
  Stack,
  Stat,
  Table,
  Text,
  useHostTheme,
} from "cursor/canvas";

const stageLabels = ["Group", "R16", "QF", "SF", "3rd", "Final"];

export default function Wc2022AnalysisStory() {
  const theme = useHostTheme();

  return (
    <Stack gap={24}>
      <Stack gap={8}>
        <H1>WC2022 Analysis Story</H1>
        <Text tone="secondary">
          StatsBomb Open Data · staging + analytics · 64 matches · validated 2026-06-14
        </Text>
      </Stack>

      <Grid columns={4} gap={12}>
        <Stat label="Matches" value="64" />
        <Stat label="Events" value="234,637" />
        <Stat label="Fact rows" value="1,996" />
        <Stat label="Pass drop under pressure" value="-12.9pp" tone="warning" />
      </Grid>

      <Callout tone="info" title="Headline">
        Knockouts are not uniformly low-scoring — intensity rises (defensive actions), but pass
        accuracy does not predict wins. Korea progressed with positive group-stage xG, then Brazil
        created 3.26 xG vs Korea&apos;s 0.34 in the R16.
      </Callout>

      <Grid columns={2} gap={16}>
        <Card>
          <CardHeader>Avg total goals per match by stage</CardHeader>
          <CardBody>
            <BarChart
              categories={stageLabels}
              series={[{ name: "Goals per match", data: [2.5, 3.5, 2.5, 2.5, 3.0, 6.0], tone: "info" }]}
              yMin={0}
              valueSuffix=""
              showValues
            />
            <Text tone="secondary" size="small">
              Source: staging.matches · WC2022
            </Text>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>Defensive actions per match by stage</CardHeader>
          <CardBody>
            <BarChart
              categories={stageLabels}
              series={[
                {
                  name: "Tackle+INT+Pressure+Block",
                  data: [340, 376, 390, 397, 335, 496],
                  tone: "neutral",
                },
              ]}
              yMin={0}
              showValues
            />
            <Text tone="secondary" size="small">
              Source: analytics.fact_player_match_stats
            </Text>
          </CardBody>
        </Card>
      </Grid>

      <Grid columns={2} gap={16}>
        <Card>
          <CardHeader>Pass completion: pressure vs calm (%)</CardHeader>
          <CardBody>
            <BarChart
              categories={["No pressure", "Under pressure"]}
              series={[{ name: "Completion %", data: [83.73, 70.84], tone: "warning" }]}
              yMin={0}
              yMax={100}
              showValues
            />
            <Text tone="secondary" size="small">
              68,515 pass attempts · staging.events
            </Text>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>Team pass accuracy by result (%)</CardHeader>
          <CardBody>
            <BarChart
              categories={["Win", "Draw", "Loss"]}
              series={[{ name: "Completion %", data: [80.76, 80.75, 80.96], tone: "neutral" }]}
              yMin={78}
              yMax={82}
              showValues
            />
            <Text tone="secondary" size="small">
              No meaningful win/loss gap
            </Text>
          </CardBody>
        </Card>
      </Grid>

      <Card>
        <CardHeader>Top chance creators (total xG)</CardHeader>
        <CardBody>
          <Table
            headers={["Player", "xG", "Goals"]}
            rows={[
              ["Messi (ARG)", "7.60", "9"],
              ["Mbappé (FRA)", "5.02", "9"],
              ["Lewandowski (POL)", "3.13", "2"],
              ["Giroud (FRA)", "3.04", "4"],
              ["Lautaro (ARG)", "2.91", "1"],
            ]}
            columnAlign={["left", "right", "right"]}
          />
        </CardBody>
      </Card>

      <Card>
        <CardHeader>South Korea — xG balance & opponent defense</CardHeader>
        <CardBody>
          <Table
            headers={["Opponent", "Score", "xG diff", "Opp def actions"]}
            rows={[
              ["Uruguay", "0-0", "+0.08", "154"],
              ["Ghana", "2-3", "+0.19", "185"],
              ["Portugal", "2-1", "+0.43", "116"],
              ["Brazil", "4-1", "-2.92", "147"],
            ]}
            columnAlign={["left", "left", "right", "right"]}
          />
          <Text tone="secondary" size="small" style={{ marginTop: 12, color: theme.text.secondary }}>
            xG diff = Korea xG − opponent xG. Opp def actions = tackles + interceptions + pressures
            + blocks.
          </Text>
        </CardBody>
      </Card>
    </Stack>
  );
}
