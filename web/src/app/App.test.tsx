import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import report from "../test/report.fixture.json";
import { App } from "./App";

function serve(body: unknown, ok = true) {
  vi.stubGlobal("fetch", vi.fn(async () => (ok ? new Response(JSON.stringify(body)) : new Response("", { status: 404 }))));
}

afterEach(() => vi.unstubAllGlobals());

test("shows a skeleton, then the overview with the patient's two projections", async () => {
  serve(report);
  render(<App />);
  expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
  expect(await screen.findByRole("heading", { name: /traced back to the dicom/i })).toBeInTheDocument();
  expect(screen.getAllByRole("img", { name: /maximum-intensity projection/i })).toHaveLength(2);
});

test("a missing report says how to make it and offers a retry", async () => {
  serve(null, false);
  render(<App />);
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent(/tep lab dev/);
  serve(report);
  await userEvent.click(screen.getByRole("button", { name: /try again/i }));
  expect(await screen.findByRole("heading", { name: /traced back to the dicom/i })).toBeInTheDocument();
});

test("the sites view flags the miscalibrated site and shows query letters", async () => {
  serve(report);
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: /sites and queries/i }));
  expect(await screen.findByText(/\(flagged\)/)).toBeInTheDocument();
  expect(screen.getAllByRole("article").length).toBeGreaterThan(0);
});

test("the evidence view lists the endpoints and every gate", async () => {
  serve(report);
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: /^evidence$/i }));
  expect(await screen.findByRole("heading", { name: /endpoints against the analysis plan/i })).toBeInTheDocument();
  const split = (report as { heldout?: typeof report.dev }).heldout ?? report.dev;
  expect(screen.getAllByText(/^(Pass|Fail)$/)).toHaveLength(split.gates.pipeline.length);
});

test("the knowledge view shows induced terms and the refusal reasons", async () => {
  serve(report);
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: /knowledge graph/i }));
  expect(await screen.findAllByText(/added as/)).toHaveLength(2);
  expect(screen.getByText(/sentence not in document/)).toBeInTheDocument();
});
