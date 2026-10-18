#!/usr/bin/env python3
"""Generate the SentinelAWS architecture diagram as an editable draw.io file.

The .drawio source is the single source of truth and is written by hand-edit
friendly draw.io primitives:

  * every AWS service uses the official AWS4 icon set that ships with draw.io
    (``shape=mxgraph.aws4.resourceIcon`` + ``resIcon``), so nothing is vendored
    and nothing is drawn from base64 blobs;
  * the VPC, Availability Zone and subnet groupings use the AWS4 group shapes;
  * every icon is placed on a fixed grid by this script, and the script refuses
    to emit a file whose icons, labels or containers overlap; a node declared
    to span two subnets (the ALB) is separately checked to straddle exactly
    those two and nothing else.

Usage:

    python3 architecture/build_drawio.py            # write the .drawio
    python3 architecture/build_drawio.py --check     # fail if the file is stale

Rendering to SVG/PNG is done by the draw.io CLI, not by this script:

    drawio --no-sandbox -x -f svg -o architecture/sentinelaws.drawio.svg \
        architecture/sentinelaws.drawio
    drawio --no-sandbox -x -f png --width 4000 -o architecture/sentinelaws.png \
        architecture/sentinelaws.drawio

Every node and container carries the Terraform resource it represents, so a
change to terraform/ that is not mirrored here is visible in review.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "sentinelaws.drawio"

# --------------------------------------------------------------------------
# Palette. Colours follow the official AWS Architecture Icon categories.
# --------------------------------------------------------------------------
FILL = {
    "networking": "#8C4FFF",
    "compute": "#ED7100",
    "database": "#C925D1",
    "security": "#DD3522",
    "management": "#E7157B",
    "integration": "#E7157B",
    "storage": "#7AA116",
    "general": "#232F3E",
}

GROUP = {
    "vpc": ("group_vpc2", "#8C4FFF"),
    "az": ("group_availability_zone", "#00A4A6"),
}

REQUEST = "#1A73E8"
DETECTION = "#D97706"
RESPONSE = "#B91C1C"
ASYNC = "#64748B"

# --------------------------------------------------------------------------
# Geometry. One grid, so the checker below can reason about collisions.
# --------------------------------------------------------------------------
ICON = 56
GAP = 22
LABEL_PAD = 46  # label block under an icon (name + sub-line)


def icon(id_, res, label, x, y, category, sub=None, parent="1", w=ICON,
         h=None, spans=None, side=None):
    return {
        "kind": "icon", "id": id_, "res": res, "label": label, "sub": sub,
        "x": x, "y": y, "w": w, "h": w if h is None else h, "parent": parent,
        "fill": FILL[category], "spans": spans, "side": side,
    }


def group(id_, label, x, y, w, h, kind, parent="1", nested=False):
    gr, color = GROUP[kind]
    return {"kind": "group", "id": id_, "label": label, "icon": gr,
            "color": color, "x": x, "y": y, "w": w, "h": h, "parent": parent,
            "nested": nested}


def box(id_, label, x, y, w, h, fill, stroke, color, parent="1", nested=False,
        align="left"):
    return {"kind": "subnet", "id": id_, "label": label, "x": x, "y": y,
            "w": w, "h": h, "parent": parent, "fill": fill, "stroke": stroke,
            "color": color, "nested": nested, "align": align}


def note(id_, label, x, y, w):
    return {"kind": "note", "id": id_, "label": label, "x": x, "y": y,
            "w": w, "h": 34, "parent": "1"}


# --------------------------------------------------------------------------
# Layout. Columns: left edge, AZ A, AZ B, then two right-hand columns.
# --------------------------------------------------------------------------
NODES: list[dict] = []
EDGES: list[dict] = []

# ---- columns -------------------------------------------------------------
DET_X = 1680      # CloudTrail, Config, Resolver, GuardDuty
OPS_X = 2200      # Security Hub, EventBridge, quarantine, ledger, alerts
WAF_X = 2500      # WAF block Lambda, WAF IP set, DLQs
BUCKET_X = 2600   # audit bucket and CloudWatch Logs

# ---- vertical stack ------------------------------------------------------
R_PUB, R_APP, R_DB = 364, 564, 764   # icon rows inside the AZ subnets
AZ_W, AZ_H, AZ_Y = 570, 625, 275     # AZ band starts below the IGW band
VPC = (410, 150, 1200, 872)          # x, y, w, h
ACCOUNT = (340, 110, 2420, 1510)

NODES += [
    # ---- internet edge ---------------------------------------------------
    box("g_internet", "Internet", 40, 105, 280, 375,
        "#F8FAFC", "#94A3B8", "#334155"),
    icon("n_users", "users", "Users", 216, 112, "general", side=True),
    icon("n_route53", "route_53", "Route 53", 100, 210, "networking",
         "hosted zone"),
    icon("n_waf", "waf", "AWS WAF", 200, 210, "security", "Web ACL on ALB"),
    icon("n_acm", "certificate_manager", "ACM", 100, 360, "security",
         "TLS certificate"),

    # ---- AWS account -----------------------------------------------------
    box("g_account", "AWS account / Region \u2014 deployment profile: ha",
        *ACCOUNT, fill="#FFFFFF", stroke="#64748B", color="#334155"),
    group("g_vpc", "VPC 10.0.0.0/16 \u2014 DNS support and hostnames enabled",
          *VPC, kind="vpc", nested=True),

    # ---- two availability zones -----------------------------------------
    group("g_aza", "Availability Zone A", 430, AZ_Y, AZ_W, AZ_H, "az",
          nested=True),
    group("g_azb", "Availability Zone B", 1010, AZ_Y, AZ_W, AZ_H, "az",
          nested=True),
]

# subnet bands inside each AZ. Titles are centred so connectors that enter the
# rows below never cross the label text.
for az, x0 in (("a", 450), ("b", 1030)):
    NODES.append(box(f"g_pub_{az}", "Public subnet", x0, R_PUB - 52,
                     AZ_W - 40, 170, "#E8F1FF", "#99BBFF", "#1F3A5F",
                     nested=True, align="center"))
    NODES.append(box(f"g_app_{az}", "Private application subnet", x0,
                     R_APP - 52, AZ_W - 40, 170, "#FFF6E5", "#EFC177",
                     "#5C4213", nested=True, align="center"))
    NODES.append(box(f"g_db_{az}", "Isolated database subnet", x0,
                     R_DB - 52, AZ_W - 40, 170, "#F2ECFF", "#B79CF0",
                     "#3B2A63", nested=True, align="center"))

NODES += [
    # ---- public subnets: NAT Gateways, IGW, ALB --------------------------
    # The load balancer is a regional resource: one node, drawn as a wide
    # capsule that spans the public subnet in each Availability Zone, so its
    # placement cannot be read as single-AZ. The audit below enforces that the
    # node straddles exactly those two subnets. The Internet Gateway belongs to
    # the VPC itself, so it sits in the VPC band above the subnets, not inside
    # one.
    icon("n_nat_a", "nat_gateway", "NAT Gateway", 470, R_PUB, "networking",
         "AZ A"),
    icon("n_igw", "internet_gateway", "Internet Gateway", 1050, 165,
         "networking"),
    icon("n_nat_b", "nat_gateway", "NAT Gateway", 1180, R_PUB, "networking",
         "AZ B"),
    icon("n_alb", "application_load_balancer", "Application Load Balancer",
         880, R_PUB, "networking", "HTTPS \u00b7 public subnet per AZ",
         w=250, h=56, spans=("g_pub_a", "g_pub_b")),

    # ---- private application subnets -------------------------------------
    icon("n_ec2_a1", "ec2", "EC2", 470, R_APP, "compute", "ASG instance"),
    icon("n_ec2_a2", "ec2", "EC2", 610, R_APP, "compute", "ASG instance"),
    icon("n_ec2_b1", "ec2", "EC2", 1050, R_APP, "compute", "ASG instance"),
    icon("n_ec2_b2", "ec2", "EC2", 1190, R_APP, "compute", "ASG instance"),

    # ---- isolated database subnets ---------------------------------------
    icon("n_rds_p", "rds_postgresql_instance", "RDS PostgreSQL", 470, R_DB,
         "database", "primary \u00b7 Multi-AZ", w=64),
    icon("n_rds_s", "rds_postgresql_instance", "RDS PostgreSQL", 1050, R_DB,
         "database", "standby", w=64),

    # ---- flow logs inside the VPC ----------------------------------------
    icon("n_flow", "flow_logs", "VPC Flow Logs", 700, 910, "networking",
         "ALL traffic"),
    icon("n_gd", "guardduty", "GuardDuty", DET_X, 905, "security",
         "S3 data events \u00b7 EBS malware", w=64),

    # ---- detection column -------------------------------------------------
    icon("n_ct", "cloudtrail", "CloudTrail", DET_X, 230, "management",
         "management events"),
    icon("n_cfg", "config", "AWS Config", DET_X, 430, "management",
         "recorder + rules"),
    icon("n_dns", "route_53_resolver", "Route 53 Resolver", DET_X, 630,
         "networking", "DNS query logs"),
    icon("n_s3", "s3", "S3", BUCKET_X, 230, "storage",
         "audit bucket \u00b7 KMS"),
    icon("n_cw", "cloudwatch_logs", "CloudWatch Logs", BUCKET_X, 430,
         "management", "log delivery"),

    # ---- response column --------------------------------------------------
    icon("n_sh", "security_hub", "Security Hub", OPS_X, 630, "security",
         "finding aggregation"),
    icon("n_eb", "eventbridge", "EventBridge", 2340, 905, "integration",
         "severity \u2265 7 rule"),
    icon("n_lq", "lambda", "Quarantine Lambda", OPS_X, 1030, "compute",
         "standby \u00b7 snapshot \u00b7 SG swap"),
    icon("n_ddb", "dynamodb", "DynamoDB", OPS_X, 1240, "database",
         "incident ledger"),
    icon("n_sns", "sns", "SNS", OPS_X, 1440,
         "integration", "alert topic"),
    icon("n_lw", "lambda", "WAF block Lambda", WAF_X, 1030, "compute",
         "block attacker IP"),
    icon("n_ipset", "filtering_rule", "WAF IP set", WAF_X, 1240,
         "security", "incident blocklist \u00b7 enforced by the ALB Web ACL"),
    icon("n_sqs", "sqs", "SQS", WAF_X, 1440,
         "integration", "encrypted DLQs"),

    # ---- annotations ------------------------------------------------------
    note("title", "SentinelAWS \u2014 three-tier architecture, HA deployment "
                  "profile (Project 8)", 40, 40, 560),
    note("note_alb", "One internet-facing ALB, drawn spanning the public "
                     "subnet in each AZ; both EC2 targets sit behind it",
         640, 40, 340),
    note("note_ssh", "Administration uses SSM Session Manager \u2014 no "
                     "inbound SSH, no bastion host", 40, 700, 270),
    note("note_gd", "GuardDuty ingests CloudTrail management events, VPC flow "
                    "logs and Resolver DNS query logs natively \u2014 no "
                    "customer log subscription is required",
         1650, 1120, 460),
    note("note_contain", "Containment pauses the instance in its Auto Scaling "
                         "group and snapshots its volumes before isolating it",
         2150, 1560, 420),
    note("legend", "Blue: request path  \u00b7  Amber: detection inputs  "
                   "\u00b7  Red: automated response  \u00b7  Grey dashed: "
                   "replication and failed deliveries", 380, 1540, 880),
]


def edge(src, dst, label, color, dashed=False, points=None, src_exit=None,
         dst_entry=None):
    EDGES.append({"src": src, "dst": dst, "label": label, "color": color,
                  "dashed": dashed, "points": points, "src_exit": src_exit,
                  "dst_entry": dst_entry})


W = "#ffffff"
edge("n_users", "n_route53", "DNS query", REQUEST,
     points=[(216, 140), (196, 140), (196, 196), (128, 196), (128, 210)])
edge("n_route53", "n_waf", "", REQUEST,
     points=[(156, 240), (200, 240)])
edge("n_waf", "n_igw", "allowed", REQUEST,
     points=[(212, 210), (212, 180), (1066, 180), (1066, 165)])
edge("n_acm", "n_alb", "TLS certificate", REQUEST,
     points=[(156, 388), (180, 388), (180, 95), (940, 95), (940, 364)])
edge("n_igw", "n_alb", "inbound HTTPS", REQUEST,
     points=[(1078, 221), (1078, 250), (1005, 250), (1005, 364)])
edge("n_alb", "n_ec2_a1", "HTTP :8080", REQUEST,
     points=[(890, 420), (890, 548), (514, 548), (514, 564)])
edge("n_alb", "n_ec2_b1", "HTTP :8080", REQUEST,
     points=[(905, 420), (905, 548), (1100, 548), (1100, 564)])
edge("n_ec2_a2", "n_rds_p", "PostgreSQL 5432 (TLS)", REQUEST,
     points=[(666, 592), (700, 592), (700, 688), (502, 688), (502, 764)])
edge("n_ec2_b2", "n_rds_p", "", REQUEST,
     points=[(1218, 592), (1250, 592), (1250, 688), (502, 688), (502, 764)])
edge("n_rds_p", "n_rds_s", "synchronous replication", ASYNC, dashed=True,
     points=[(534, 796), (1050, 796)])
edge("n_ec2_a1", "n_nat_a", "egress via NAT", REQUEST,
     points=[(480, 564), (480, 504), (690, 504), (690, 392), (526, 392)])
edge("n_ec2_b1", "n_nat_b", "egress via NAT", REQUEST,
     points=[(1075, 564), (1075, 504), (1160, 504), (1160, 392), (1180, 392)])
edge("n_nat_a", "n_igw", "", REQUEST,
     points=[(498, 364), (498, 340), (610, 340), (610, 190), (1050, 190)])
edge("n_nat_b", "n_igw", "", REQUEST,
     points=[(1208, 364), (1208, 205), (1106, 205)])

edge("n_flow", "n_gd", "VPC flow logs (native)", DETECTION,
     points=[(756, 938), (1680, 938)])
edge("n_flow", "n_cw", "flow log delivery", DETECTION,
     points=[(700, 938), (680, 938), (680, 1050), (2160, 1050), (2160, 460),
             (2600, 460)])
edge("n_ct", "n_gd", "management events (native)", DETECTION,
     points=[(1744, 262), (1790, 262), (1790, 905), (1744, 905)])
edge("n_ct", "n_s3", "audit trail", DETECTION,
     points=[(1744, 275), (2600, 275)])
edge("n_ct", "n_cw", "log delivery", DETECTION,
     points=[(1744, 240), (2560, 240), (2560, 430), (2600, 430)])
edge("n_cfg", "n_s3", "configuration history", DETECTION,
     points=[(1680, 458), (1640, 458), (1640, 210), (2628, 210),
             (2628, 230)])
edge("n_dns", "n_gd", "DNS query logs (native)", DETECTION,
     points=[(1712, 694), (1712, 905)])

edge("n_gd", "n_sh", "findings", RESPONSE,
     points=[(1744, 953), (2180, 953), (2180, 662), (2200, 662)])
edge("n_gd", "n_eb", "findings (severity \u2265 7)", RESPONSE,
     points=[(1744, 937), (2340, 937)])
edge("n_eb", "n_lw", "", RESPONSE,
     points=[(2404, 937), (2532, 937), (2532, 1030)])
edge("n_eb", "n_lq", "", RESPONSE,
     points=[(2372, 969), (2372, 1062), (2264, 1062)])
edge("n_lq", "n_ec2_b2", "EnterStandby + snapshot, then swap instance SG",
     RESPONSE, points=[(2200, 1062), (1290, 1062), (1290, 592), (1246, 592)])
edge("n_lw", "n_ipset", "wafv2:UpdateIPSet", RESPONSE,
     points=[(2452, 1094), (2452, 1240)])
edge("n_ipset", "n_waf", "IP set reference", RESPONSE,
     points=[(2556, 1268), (2700, 1268), (2700, 1634), (330, 1634),
             (330, 140), (300, 140), (300, 196), (240, 196), (240, 210)])
edge("n_lq", "n_ddb", "incident record", RESPONSE,
     points=[(2232, 1094), (2232, 1240)])
edge("n_lw", "n_ddb", "", RESPONSE,
     points=[(2420, 1080), (2340, 1080), (2340, 1272), (2264, 1272)])
edge("n_ddb", "n_sns", "alert", RESPONSE, points=[(2232, 1304), (2232, 1440)])
edge("n_lw", "n_sns", "", RESPONSE,
     points=[(2564, 1060), (2620, 1060), (2620, 1400), (2232, 1400),
             (2232, 1440)])
edge("n_eb", "n_sqs", "failed deliveries", ASYNC, dashed=True,
     points=[(2404, 953), (2680, 953), (2680, 1468), (2564, 1468)])


# --------------------------------------------------------------------------
# Overlap checker. Icons (with their label block), notes and the nesting order
# of containers must all be collision free.
# --------------------------------------------------------------------------
SINGLE_LABEL_PAD = 24  # label block of an icon without a sub-line
SIDE_LABEL_PAD = 2     # label placed beside the icon, not below it


def bbox(node):
    if node["kind"] == "icon":
        if node.get("side"):
            pad = SIDE_LABEL_PAD
        elif node.get("sub"):
            pad = LABEL_PAD
        else:
            pad = SINGLE_LABEL_PAD
        h = node["h"] + pad
    else:
        h = node["h"]
    return (node["x"], node["y"], node["x"] + node["w"], node["y"] + h)


def contains(outer, inner):
    ox, oy, ox2, oy2 = outer
    ix, iy, ix2, iy2 = inner
    return ox <= ix and oy <= iy and ix2 <= ox2 and iy2 <= oy2


def overlaps(a, b):
    ax, ay, ax2, ay2 = a
    bx, by, bx2, by2 = b
    return not (ax2 <= bx or bx2 <= ax or ay2 <= by or by2 <= ay)


def audit(nodes):
    problems = []
    icons = [n for n in nodes if n["kind"] == "icon"]
    notes = [n for n in nodes if n["kind"] == "note"]
    boxes = [n for n in nodes if n["kind"] in ("group", "subnet")]
    by_id = {n["id"]: n for n in nodes}

    for index, first in enumerate(icons):
        for second in icons[index + 1:]:
            if overlaps(bbox(first), bbox(second)):
                problems.append(
                    f"icons overlap: {first['id']} and {second['id']}")

    # An element inside a container is only a problem when it also leaves that
    # container. Nested containers must be strictly inside their parent except
    # for the top band (about 34px) reserved for the parent's own label; that is
    # the declared layout, not a defect. Declared spanning nodes are exempt and
    # are checked by the dedicated rule below.
    NAME_BAND = 34
    for first in icons + notes:
        if first.get("spans"):
            continue
        box = bbox(first)
        for second in boxes:
            host = bbox(second)
            if overlaps(box, host) and not contains(host, box):
                problems.append(
                    f"{first['id']} leaves container {second['id']}")

    for index, first in enumerate(boxes):
        for second in boxes[index + 1:]:
            a, b = bbox(first), bbox(second)
            if not overlaps(a, b):
                continue
            a_in_b = contains(b, a)
            b_in_a = contains(a, b)
            if a_in_b or b_in_a:
                inner, outer = (first, second) if a_in_b else (second, first)
                if not by_id[inner["id"]].get("nested") and not by_id[
                        outer["id"]].get("nested"):
                    problems.append(
                        f"nested containers declared without nested=True: "
                        f"{inner['id']} in {outer['id']}")
                host = bbox(outer)
                child = bbox(inner)
                if child[1] < host[1] + NAME_BAND - 1:
                    problems.append(
                        f"{inner['id']} is inside {outer['id']}'s label band")
                continue
            problems.append(
                f"containers overlap: {first['id']} and {second['id']}")

    # A declared spanning node crosses container borders on purpose. It must
    # overlap every container it declares it spans, must not be contained by
    # any of them (if it were, the placement would read as single-container),
    # and must not touch any container outside the span's ancestry.
    for node in icons:
        if not node.get("spans"):
            continue
        node_box = bbox(node)
        allowed = set()
        for target_id in node["spans"]:
            target = by_id[target_id]
            target_box = bbox(target)
            if not overlaps(node_box, target_box):
                problems.append(
                    f"spanning node {node['id']} does not overlap {target_id}")
            if contains(target_box, node_box):
                problems.append(
                    f"spanning node {node['id']} is contained in {target_id}")
            allowed.add(target_id)
            allowed.update(
                b["id"] for b in boxes if contains(bbox(b), target_box))
        for container in boxes:
            if (overlaps(node_box, bbox(container))
                    and container["id"] not in allowed):
                problems.append(
                    f"spanning node {node['id']} overlaps non-span container "
                    f"{container['id']}")

    # A connector must not run through an icon or its label block, except at the
    # two endpoints the connector is declared to attach to. Endpoints sit on the
    # icon border, so they are excluded by icon id rather than by distance.
    def segment_hits_icon(p, q, box, pad=1.0):
        bx, by, bx2, by2 = box
        bx, by, bx2, by2 = bx + pad, by + pad, bx2 - pad, by2 - pad
        length = max(abs(q[0] - p[0]), abs(q[1] - p[1]))
        steps = max(int(length), 1)
        for step in range(steps + 1):
            t = step / steps
            x = p[0] + (q[0] - p[0]) * t
            y = p[1] + (q[1] - p[1]) * t
            if bx < x < bx2 and by < y < by2:
                return True
        return False

    for index, e in enumerate(EDGES, start=1):
        if not e["points"]:
            continue
        for p, q in zip(e["points"], e["points"][1:]):
            for node in icons + notes:
                if node["id"] in (e["src"], e["dst"]):
                    continue
                if segment_hits_icon(p, q, bbox(node)):
                    problems.append(
                        f"connector e{index} ({e['src']} -> {e['dst']}) crosses "
                        f"{node['id']}")

    for node in nodes:
        if node["x"] < 0 or node["y"] < 0:
            problems.append(f"{node['id']} has a negative coordinate")
    return problems


# --------------------------------------------------------------------------
# Emit
# --------------------------------------------------------------------------
def esc(value: str) -> str:
    return (value.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def style_for(node) -> str:
    if node["kind"] == "icon":
        label_pos = (
            "labelPosition=right;verticalLabelPosition=middle;align=left;"
            "spacingLeft=4;" if node.get("side") else
            "verticalLabelPosition=bottom;verticalAlign=top;align=center;")
        return (
            f"sketch=0;outlineConnect=0;fontColor=#232F3E;"
            f"fillColor={node['fill']};strokeColor=#ffffff;dashed=0;"
            f"{label_pos}"
            f"html=1;fontSize=12;fontStyle=0;aspect=fixed;"
            f"shape=mxgraph.aws4.resourceIcon;"
            f"resIcon=mxgraph.aws4.{node['res']};"
        )
    if node["kind"] == "group":
        return (
            f"shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.{node['icon']};"
            f"strokeColor={node['color']};fillColor=none;verticalAlign=top;"
            f"align=left;spacingLeft=30;fontColor={node['color']};dashed=0;"
            f"fontSize=13;fontStyle=1;html=1;"
        )
    if node["kind"] == "subnet":
        return (
            f"rounded=1;arcSize=4;fillColor={node['fill']};"
            f"strokeColor={node['stroke']};verticalAlign=top;"
            f"align={node['align']};spacingLeft=10;spacingTop=6;"
            f"fontColor={node['color']};fontSize=12;fontStyle=1;html=1;"
        )
    return (
        f"rounded=1;arcSize=10;fillColor=#F1F5F9;strokeColor=#94A3B8;"
        f"verticalAlign=middle;align=center;fontColor=#334155;fontSize=11;"
        f"html=1;whiteSpace=wrap;"
    )


def value_for(node) -> str:
    """Display text, unescaped. HTML labels are escaped once by the emitter."""
    if node["kind"] == "icon":
        if node.get("sub"):
            return (f"{node['label']}<br>"
                    f"<font style=\"font-size:10px;color:#64748B\">"
                    f"{node['sub']}</font>")
        return node["label"]
    return node["label"]


def edge_style(e) -> str:
    dash = "dashed=1;dashPattern=8 4;" if e["dashed"] else ""
    return (
        f"edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;"
        f"strokeColor={e['color']};strokeWidth=2;{dash}"
        f"endArrow=block;endFill=1;fontColor={e['color']};fontSize=11;"
        f"labelBackgroundColor=#FFFFFF;"
    )


def build_xml(nodes) -> str:
    lines = [
        '<mxfile host="app.diagrams.net" type="device">',
        '  <diagram id="sentinelaws" name="SentinelAWS">',
        '    <mxGraphModel dx="1600" dy="1200" grid="0" gridSize="10" '
        'guides="1" tooltips="1" connect="1" arrows="1" fold="1" '
        'page="1" pageScale="1" pageWidth="2800" pageHeight="1650" '
        'math="0" shadow="0">',
        "      <root>",
        '        <mxCell id="0"/>',
        '        <mxCell id="1" parent="0"/>',
    ]
    for node in nodes:
        lines.append(
            f'        <mxCell id="{node["id"]}" value="{esc(value_for(node))}" '
            f'style="{esc(style_for(node))}" vertex="1" parent="{node["parent"]}">'
        )
        lines.append(
            f'          <mxGeometry x="{node["x"]}" y="{node["y"]}" '
            f'width="{node["w"]}" height="{node["h"]}" as="geometry"/>'
        )
        lines.append("        </mxCell>")
    for index, e in enumerate(EDGES, start=1):
        points = ""
        if e["points"]:
            first, *middle, last = e["points"]
            array = "".join(
                f'<mxPoint x="{x}" y="{y}"/>' for x, y in middle)
            points = (
                f'<mxPoint x="{first[0]}" y="{first[1]}" as="sourcePoint"/>'
                f'<Array as="points">{array}</Array>'
                f'<mxPoint x="{last[0]}" y="{last[1]}" as="targetPoint"/>'
            )
        lines.append(
            f'        <mxCell id="e{index}" value="{esc(e["label"])}" '
            f'style="{edge_style(e)}" edge="1" parent="1" '
            f'source="{e["src"]}" target="{e["dst"]}">'
        )
        lines.append(f"          <mxGeometry relative=\"1\" as=\"geometry\">"
                     f"{points}</mxGeometry>")
        lines.append("        </mxCell>")
    lines += ["      </root>", "    </mxGraphModel>", "  </diagram>",
              "</mxfile>"]
    return "\n".join(lines) + "\n"


def main(argv):
    problems = audit(NODES)
    if problems:
        for problem in problems:
            print("LAYOUT: " + problem)
        return 2

    xml = build_xml(NODES)
    ET.fromstring(xml)  # well-formedness gate

    if "--check" in argv:
        if not OUT.is_file() or OUT.read_text() != xml:
            print(f"{OUT.name} is stale; run python3 architecture/build_drawio.py")
            return 1
        print("architecture/sentinelaws.drawio is up to date")
        return 0

    OUT.write_text(xml)
    print(f"wrote {OUT.name}: {len(NODES)} nodes, {len(EDGES)} edges, "
          f"{OUT.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))