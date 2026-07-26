import { useEffect, useMemo, useRef } from "react";
import * as d3 from "d3";
import type { BlastRadiusGraph } from "../lib/api";

type SimNode = d3.SimulationNodeDatum & { id: string; type: string; label: string };
type Link = d3.SimulationLinkDatum<SimNode> & { label: string };

function colorForType(type: string) {
  if (type === "agent") return "#58a6ff";
  if (type === "tool") return "#d29922";
  if (type === "data_store") return "#bc8cff";
  return "#7d8590";
}

export default function BlastRadiusGraphView(props: { graph: BlastRadiusGraph; height?: number }) {
  const ref = useRef<SVGSVGElement | null>(null);
  const height = props.height ?? 560;

  const { nodes, links } = useMemo(() => {
    const nodes: SimNode[] = props.graph.nodes.map((n) => ({ ...n }));
    const links: Link[] = props.graph.edges.map((e) => ({ source: e.source, target: e.target, label: e.label }));
    return { nodes, links };
  }, [props.graph]);

  useEffect(() => {
    const svg = d3.select(ref.current);
    svg.selectAll("*").remove();

    const width = ref.current?.clientWidth || 900;
    svg.attr("viewBox", `0 0 ${width} ${height}`);

    const sim = d3
      .forceSimulation(nodes)
      .force("link", d3.forceLink<SimNode, Link>(links).id((d) => d.id).distance(90))
      .force("charge", d3.forceManyBody().strength(-380))
      .force("center", d3.forceCenter(width / 2, height / 2));

    const g = svg.append("g");

    const link = g
      .append("g")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke", "#30363d")
      .attr("stroke-width", 1);

    const node = g
      .append("g")
      .selectAll("circle")
      .data(nodes)
      .join("circle")
      .attr("r", (d) => (d.type === "agent" ? 14 : d.type === "tool" ? 10 : 8))
      .attr("fill", (d) => colorForType(d.type))
      .attr("stroke", "#0d1117")
      .attr("stroke-width", 2)
      .call(
        d3
          .drag<SVGCircleElement, SimNode>()
          .on("start", (event, d) => {
            if (!event.active) sim.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on("drag", (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on("end", (event, d) => {
            if (!event.active) sim.alphaTarget(0);
            d.fx = undefined;
            d.fy = undefined;
          }) as unknown as (
            selection: d3.Selection<SVGCircleElement | d3.BaseType, SimNode, SVGGElement, unknown>
          ) => void
      );

    const labels = g
      .append("g")
      .selectAll("text")
      .data(nodes)
      .join("text")
      .text((d) => d.label)
      .attr("font-size", 10)
      .attr("fill", "#e6edf3")
      .attr("opacity", 0.9);

    sim.on("tick", () => {
      link
        .attr("x1", (d) => (d.source as SimNode).x ?? 0)
        .attr("y1", (d) => (d.source as SimNode).y ?? 0)
        .attr("x2", (d) => (d.target as SimNode).x ?? 0)
        .attr("y2", (d) => (d.target as SimNode).y ?? 0);

      node.attr("cx", (d) => d.x ?? 0).attr("cy", (d) => d.y ?? 0);
      labels.attr("x", (d) => (d.x ?? 0) + 12).attr("y", (d) => (d.y ?? 0) + 4);
    });

    const zoom = d3.zoom<SVGSVGElement, unknown>().on("zoom", (event) => {
      g.attr("transform", event.transform);
    });
    svg.call(zoom as any);

    return () => {
      sim.stop();
    };
  }, [nodes, links, height]);

  return (
    <div className="w-full bg-bg border border-border rounded-lg overflow-hidden">
      <div className="p-2 text-xs text-muted flex gap-3 items-center border-b border-border">
        <span className="inline-flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ background: "#58a6ff" }} />
          agent
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ background: "#d29922" }} />
          tool
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ background: "#7d8590" }} />
          system
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ background: "#bc8cff" }} />
          data_store
        </span>
      </div>
      <svg ref={ref} className="w-full" style={{ height }} />
    </div>
  );
}

