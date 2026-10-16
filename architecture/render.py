#!/usr/bin/env python3
"""Render the SentinelAWS architecture diagram from one declarative model.

A single in-file model emits three artifacts, so the picture and the text
source can no longer drift apart:

    architecture/sentinelaws.svg    editable vector original (hand-placed)
    architecture/sentinelaws.png    README image, exported at 4x
    architecture/sentinelaws.mmd    Mermaid text view, generated from the
                                    same nodes and edges as the SVG

Usage:

    python3 architecture/render.py            # regenerate all three
    python3 architecture/render.py --check    # fail if committed files differ

The official AWS Architecture Icons are vendored in ``architecture/icons/``,
so no third-party package, Graphviz, or network access is required. Only the
PNG export needs ``pip install cairosvg``; the SVG and Mermaid views render
without it.

Every node and edge is grounded in terraform/ - the comments name the module
and resource each element represents, so an infrastructure change that is not
reflected here shows up as a diagram/implementation divergence in review.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ICON_DIR = HERE / "icons"
SVG_OUT = HERE / "sentinelaws.svg"
PNG_OUT = HERE / "sentinelaws.png"
MMD_OUT = HERE / "sentinelaws.mmd"

BLUE = "#1a73e8"  # request path
ORANGE = "#e67e22"  # detection inputs
RED = "#c0392b"  # automated response
GRAY = "#7f8c8d"  # async / replication

# --------------------------------------------------------------------------
# Container tree for the generated Mermaid view. Drawn boxes reference these
# ids, and every node declares its membership through ``gid``.
# --------------------------------------------------------------------------
CONTAINERS = [
    ("internet", "Internet", None),
    ("account", "AWS account / Region - deployment profile: ha", None),
    ("vpc", "VPC - DNS support and hostnames enabled (terraform: networking module)", "account"),
    ("aza", "Availability Zone A", "vpc"),
    ("puba", "Public subnet AZ A", "aza"),
    ("appa", "Private application subnet AZ A", "aza"),
    ("dba", "Isolated database subnet AZ A", "aza"),
    ("azb", "Availability Zone B", "vpc"),
    ("pubb", "Public subnet AZ B", "azb"),
    ("appb", "Private application subnet AZ B", "azb"),
    ("dbb", "Isolated database subnet AZ B", "azb"),
]

# --------------------------------------------------------------------------
# The model. Order is draw order: containers, then their contents, then every
# edge on top. Edge entries carrying ``link`` become Mermaid edges; segments
# without it are pure routing geometry and stay SVG-only.
# --------------------------------------------------------------------------
DRAW: list[tuple[str, dict]] = [
    # ---- title -----------------------------------------------------------
    ("text", dict(x=30, y=42, size=22, weight="700", fill="#0f172a",
                  text="SentinelAWS \u2014 Architecture (hardened / HA deployment profile)")),

    # ---- left edge: internet --------------------------------------------
    ("text_box", dict(id="internet_users", shape="stadium",
                      x=30, y=95, w=130, h=60, label="Internet users",
                      gid="internet")),
    ("node", dict(id="route53", icon="route53", x=198, y=93, size=64,
                  shape="stadium", label="Route 53", sub="DNS", gid="account")),
    ("node", dict(id="waf", icon="waf", x=198, y=238, size=64,
                  label="AWS WAF", sub="Web ACL on ALB", gid="account")),
    ("node", dict(id="acm", icon="acm", x=63, y=238, size=64,
                  label="ACM", sub="TLS certificate", gid="account")),

    # ---- VPC -------------------------------------------------------------
    ("box", dict(x=350, y=60, w=800, h=940,
                 label="VPC \u2014 DNS support + hostnames enabled",
                 fill="#f8fafc", stroke="#94a3b8", gid="vpc")),
    ("node", dict(id="igw", icon="igw", x=390, y=100, size=48, label=None,
                  mmd="Internet Gateway", gid="vpc")),
    ("text", dict(x=414, y=170, size=12, weight="600", fill="#1e293b",
                  text="Internet Gateway", anchor="middle")),

    # ---- availability zones (terraform: networking module, 2 AZs) --------
    ("box", dict(x=370, y=185, w=370, h=785, label="Availability Zone A",
                 fill="#ffffff", stroke="#cbd5e1", label_pos="bottom",
                 gid="aza")),
    ("box", dict(x=760, y=185, w=370, h=785, label="Availability Zone B",
                 fill="#ffffff", stroke="#cbd5e1", label_pos="bottom",
                 gid="azb")),

    # ---- public subnets: ALB + NAT --------------------------------------
    # terraform: aws_lb and aws_nat_gateway are both created in the public
    # subnets; one NAT Gateway per AZ in the ha profile.
    ("box", dict(x=385, y=230, w=340, h=150, label="Public subnets",
                 fill="#eff6ff", stroke="#bfdbfe", size=12, gid="puba")),
    ("box", dict(x=775, y=230, w=340, h=150, label="Public subnets",
                 fill="#eff6ff", stroke="#bfdbfe", size=12, gid="pubb")),
    ("node", dict(id="alb", icon="alb", x=719, y=262, size=72,
                  label="Application Load Balancer", sub="public \u00b7 HTTPS",
                  mmd="Application Load Balancer - public subnets, AZ A + AZ B",
                  gid="vpc")),
    ("node", dict(id="nata", icon="nat", x=442, y=272, size=56,
                  label="NAT Gateway", sub="AZ A", gid="puba")),
    ("node", dict(id="natb", icon="nat", x=1012, y=272, size=56,
                  label="NAT Gateway", sub="AZ B", gid="pubb")),
    # The ALB node sits on the boundary between the two public subnets, so the
    # placement is captioned rather than left to be read as "outside a subnet".
    ("text", dict(x=640, y=252, size=11, weight="600", fill="#1d4ed8",
                  text="ALB spans both public subnets (AZ A + AZ B)",
                  anchor="middle")),

    # ---- private application subnets ------------------------------------
    # terraform: application module, aws_autoscaling_group + launch template
    # in the private application subnets.
    ("box", dict(x=385, y=405, w=340, h=160, label="Private application subnets",
                 fill="#fefce8", stroke="#fde68a", size=12, gid="appa")),
    ("box", dict(x=775, y=405, w=340, h=160, label="Private application subnets",
                 fill="#fefce8", stroke="#fde68a", size=12, gid="appb")),
    ("node", dict(id="ec2a1", icon="ec2", x=442, y=452, size=56, label=None,
                  mmd="EC2 instance - ASG (AZ A)", gid="appa")),
    ("node", dict(id="ec2a2", icon="ec2", x=552, y=452, size=56, label=None,
                  mmd="EC2 instance - ASG (AZ A)", gid="appa")),
    ("node", dict(id="ec2b1", icon="ec2", x=832, y=452, size=56, label=None,
                  mmd="EC2 instance - ASG (AZ B)", gid="appb")),
    ("node", dict(id="ec2b2", icon="ec2", x=942, y=452, size=56, label=None,
                  mmd="EC2 instance - ASG (AZ B)", gid="appb")),
    ("text", dict(x=470, y=552, size=12, weight="600", fill="#1e293b",
                  text="EC2 Auto Scaling Group", anchor="middle")),
    ("text", dict(x=880, y=552, size=12, weight="600", fill="#1e293b",
                  text="EC2 Auto Scaling Group", anchor="middle")),

    # ---- isolated database subnets --------------------------------------
    # terraform: database module, aws_db_instance multi_az = true in the ha
    # profile, no internet route from the DB subnets.
    ("box", dict(x=385, y=590, w=340, h=160, label="Isolated DB subnets",
                 fill="#f1f5f9", stroke="#cbd5e1", size=12, gid="dba")),
    ("box", dict(x=775, y=590, w=340, h=160, label="Isolated DB subnets",
                 fill="#f1f5f9", stroke="#cbd5e1", size=12, gid="dbb")),
    ("node", dict(id="rds_primary", icon="rds", x=493, y=622, size=64,
                  shape="cylinder", label="RDS PostgreSQL",
                  sub="primary \u00b7 Multi-AZ", gid="dba")),
    ("node", dict(id="rds_standby", icon="rds", x=883, y=622, size=64,
                  shape="cylinder", label="RDS PostgreSQL", sub="standby",
                  gid="dbb")),

    # ---- VPC Flow Logs (terraform: networking module, aws_flow_log) ------
    ("node", dict(id="flowlogs", icon="flowlogs", x=727, y=830, size=56,
                  label="VPC Flow Logs", sub="ALL traffic", gid="vpc")),

    # ---- right panel: detection and response -----------------------------
    # terraform: security module -> CloudTrail, Config; detection module ->
    # GuardDuty, Security Hub; remediation module -> Lambdas, ledger, DLQs.
    ("node", dict(id="cloudtrail", icon="cloudtrail", x=1258, y=100, size=64,
                  label="CloudTrail", sub="management events", gid="account")),
    ("node", dict(id="config", icon="config", x=1258, y=250, size=64,
                  label="AWS Config", sub="recorder + rules", gid="account")),
    ("node", dict(id="s3", icon="s3", x=1488, y=150, size=64, shape="cylinder",
                  label="S3", sub="audit bucket (encrypted)", gid="account")),
    ("node", dict(id="cloudwatch", icon="cloudwatch", x=1488, y=300, size=64,
                  label="CloudWatch", sub="Logs", gid="account")),
    ("node", dict(id="dnslogs", icon="route53", x=1262, y=400, size=56,
                  label="Route 53 Resolver", sub="DNS query logs",
                  gid="account")),
    ("node", dict(id="guardduty", icon="guardduty", x=1398, y=440, size=72,
                  label="GuardDuty", sub="S3 data events \u00b7 EBS malware",
                  gid="account")),
    ("node", dict(id="sechub", icon="sechub", x=1258, y=590, size=60,
                  label="Security Hub", sub="finding aggregation",
                  gid="account")),
    ("node", dict(id="eventbridge", icon="eventbridge", x=1508, y=590, size=60,
                  label="EventBridge", sub="severity \u2265 7 rule",
                  gid="account")),
    ("node", dict(id="quarantine_lambda", icon="lambda", x=1258, y=740, size=60,
                  label="Quarantine Lambda",
                  sub="standby \u00b7 snapshot \u00b7 SG swap", gid="account")),
    ("node", dict(id="waf_lambda", icon="lambda", x=1508, y=740, size=60,
                  label="WAF block Lambda", sub="block attacker IP",
                  gid="account")),
    ("node", dict(id="ipset", icon="ipset", x=1508, y=880, size=56,
                  label="WAF IP set", sub="incident blocklist", gid="account")),
    ("node", dict(id="dynamodb", icon="dynamodb", x=1258, y=880, size=56,
                  shape="cylinder", label="DynamoDB", sub="incident ledger",
                  gid="account")),
    ("node", dict(id="sns", icon="sns", x=1328, y=1010, size=52,
                  label="SNS", sub="alert topic", gid="account")),
    ("node", dict(id="sqs", icon="sqs", x=1470, y=1010, size=52,
                  shape="cylinder", label="SQS", sub="encrypted DLQs",
                  gid="account")),

    # ===================== request path (blue) ============================
    ("edge", dict(points=[(160, 125), (196, 125)], kind=BLUE,
                  link=("internet_users", "route53"), label="DNS query")),
    # Route 53 -> WAF jogs right of the node labels (x=300 gutter)
    ("edge", dict(points=[(264, 140), (300, 140), (300, 262), (266, 262)],
                  kind=BLUE, link=("route53", "waf"))),
    # WAF -> IGW. The x=320 vertical stays clear of the IGW label.
    ("edge", dict(points=[(264, 270), (320, 270), (320, 124), (388, 124)],
                  kind=BLUE, link=("waf", "igw"))),
    ("edge", dict(points=[(440, 124), (755, 124), (755, 260)], kind=BLUE,
                  label="inbound HTTPS", label_at=(600, 114),
                  link=("igw", "alb"))),
    # ACM -> ALB (TLS): routed above the public subnet bands, arrow lands on
    # the ALB icon's top edge.
    ("edge", dict(points=[(262, 262), (320, 262), (320, 208), (730, 208),
                          (730, 260)], kind=BLUE, label="TLS certificate",
                  label_at=(610, 198), link=("acm", "alb"))),
    # ALB -> EC2 targets. The trunk splits around the ALB labels: two
    # verticals at x=650/860, clear of the centered label strip.
    ("edge", dict(points=[(719, 334), (650, 334), (650, 445)], kind=BLUE,
                  link=("alb", "ec2a1"), label="HTTP :8080")),
    ("edge", dict(points=[(791, 334), (860, 334), (860, 445)], kind=BLUE,
                  link=("alb", "ec2b1"))),
    ("edge", dict(points=[(500, 445), (1000, 445)], kind=BLUE, arrow=False)),
    ("edge", dict(points=[(470, 445), (470, 450)], kind=BLUE)),
    ("edge", dict(points=[(580, 445), (580, 450)], kind=BLUE)),
    ("edge", dict(points=[(860, 445), (860, 450)], kind=BLUE)),
    ("edge", dict(points=[(970, 445), (970, 450)], kind=BLUE)),
    # EC2 -> RDS primary (writer endpoint). Stubs rise from the right-hand
    # instance of each AZ, join at y=578 (the gap between the subnet bands),
    # then drop into the primary's top edge.
    ("edge", dict(points=[(608, 510), (620, 510), (620, 578)], kind=BLUE,
                  link=("ec2a2", "rds_primary"), label="PostgreSQL 5432 (TLS)")),
    ("edge", dict(points=[(998, 510), (1000, 510), (1000, 578)], kind=BLUE,
                  link=("ec2b2", "rds_primary"))),
    ("edge", dict(points=[(1000, 578), (550, 578), (550, 620)], kind=BLUE)),
    # RDS replication (gray dashed)
    ("edge", dict(points=[(589, 654), (881, 654)], kind=GRAY,
                  label="synchronous replication", label_at=(735, 644),
                  dashed=True, link=("rds_primary", "rds_standby"))),
    # EC2 egress via NAT -> IGW. The AZ-A vertical is offset to x=525 so it
    # does not cross the Internet Gateway label.
    ("edge", dict(points=[(470, 450), (470, 344)], kind=BLUE,
                  link=("ec2a1", "nata"))),
    ("edge", dict(points=[(970, 450), (970, 400), (1040, 400), (1040, 344)],
                  kind=BLUE, link=("ec2b2", "natb"))),
    ("edge", dict(points=[(470, 268), (525, 268), (525, 124), (442, 124)],
                  kind=BLUE, label="egress via NAT", label_at=(525, 190),
                  rotate_label=True, link=("nata", "igw"))),
    # AZ-B egress runs in the x=1110 gutter, clear of the NAT-B labels.
    ("edge", dict(points=[(1040, 268), (1110, 268), (1110, 124), (760, 124)],
                  kind=BLUE, link=("natb", "igw"))),

    # ===================== detection inputs (orange) ======================
    # GuardDuty ingests CloudTrail management events, VPC flow logs, and
    # Route 53 Resolver DNS query logs natively - no customer-side log
    # subscription is required, which is what the labels record. The CloudTrail
    # vertical jogs to x=1385, clear of the Config labels.
    ("edge", dict(points=[(1360, 164), (1385, 164), (1385, 400), (1400, 400),
                          (1400, 438)], kind=ORANGE,
                  label="management events (native)", label_at=(1385, 280),
                  rotate_label=True, link=("cloudtrail", "guardduty"))),
    ("edge", dict(points=[(1392, 145), (1486, 178)], kind=ORANGE,
                  label="audit trail", label_at=(1440, 148),
                  link=("cloudtrail", "s3"))),
    ("edge", dict(points=[(1354, 132), (1455, 132), (1455, 332), (1486, 332)],
                  kind=ORANGE, label="log delivery", label_at=(1465, 230),
                  rotate_label=True, link=("cloudtrail", "cloudwatch"))),
    ("edge", dict(points=[(1324, 315), (1430, 315), (1430, 205), (1486, 205)],
                  kind=ORANGE, label="configuration history",
                  label_at=(1395, 335), link=("config", "s3"))),
    ("edge", dict(points=[(783, 886), (1205, 886), (1205, 476), (1396, 476)],
                  kind=ORANGE, label="VPC flow logs (native)",
                  label_at=(1215, 680), rotate_label=True,
                  link=("flowlogs", "guardduty"))),
    ("edge", dict(points=[(783, 865), (1420, 865), (1420, 364), (1486, 364)],
                  kind=ORANGE, label="flow log delivery", label_at=(1420, 600),
                  rotate_label=True, link=("flowlogs", "cloudwatch"))),
    ("edge", dict(points=[(1320, 428), (1396, 470)], kind=ORANGE,
                  label="DNS query logs (native)", label_at=(1358, 436),
                  link=("dnslogs", "guardduty"))),

    # ===================== automated response (red) =======================
    ("edge", dict(points=[(1430, 512), (1318, 512), (1318, 588)], kind=RED,
                  label="findings", label_at=(1318, 550), rotate_label=True,
                  link=("guardduty", "sechub"))),
    ("edge", dict(points=[(1470, 512), (1538, 512), (1538, 588)], kind=RED,
                  label="findings (severity \u2265 7)", label_at=(1548, 550),
                  rotate_label=True, link=("guardduty", "eventbridge"))),
    ("edge", dict(points=[(1506, 650), (1318, 650), (1318, 738)], kind=RED,
                  link=("eventbridge", "quarantine_lambda"))),
    # EventBridge -> WAF-block Lambda: routed around the right side so no
    # edge crosses the EventBridge labels.
    ("edge", dict(points=[(1568, 640), (1625, 640), (1625, 770), (1570, 770)],
                  kind=RED, link=("eventbridge", "waf_lambda"))),
    # The Quarantine function acts directly on the instance: first it pauses
    # the instance in its Auto Scaling Group (autoscaling:EnterStandby, so the
    # ELB health check cannot replace it and destroy the evidence), then
    # snapshots the attached EBS volumes (ec2:CreateSnapshot), then swaps every
    # ENI to the quarantine security group (ec2:ModifyNetworkInterfaceAttribute).
    # terraform: remediation module IAM statements.
    ("edge", dict(points=[(1256, 770), (1175, 770), (1175, 498), (1028, 498)],
                  kind=RED,
                  label="EnterStandby + snapshot, then swap instance SG",
                  label_at=(1165, 640), rotate_label=True,
                  link=("quarantine_lambda", "ec2b2"))),
    # WAF Lambda updates the WAF IP set (terraform: wafv2:UpdateIPSet on the
    # incident blocklist referenced by the ALB's Web ACL). Routed around the
    # Lambda's own label via the icon's right edge.
    ("edge", dict(points=[(1570, 775), (1605, 775), (1605, 908), (1566, 908)],
                  kind=RED, label="wafv2:UpdateIPSet", label_at=(1618, 845),
                  rotate_label=True, link=("waf_lambda", "ipset"))),
    ("edge", dict(points=[(1506, 908), (1210, 908), (1210, 1020), (345, 1020),
                          (345, 302), (264, 302)], kind=RED,
                  label="blocklist enforced by Web ACL", label_at=(700, 1010),
                  link=("ipset", "waf"))),
    # Incident ledger + alerts (routed below the Lambdas' own labels)
    ("edge", dict(points=[(1270, 845), (1235, 845), (1235, 908), (1256, 908)],
                  kind=RED, link=("quarantine_lambda", "dynamodb"))),
    ("edge", dict(points=[(1506, 790), (1420, 790), (1420, 908), (1316, 908)],
                  kind=RED, label="incident record", label_at=(1412, 850),
                  rotate_label=True, link=("waf_lambda", "dynamodb"))),
    ("edge", dict(points=[(1320, 936), (1350, 936), (1350, 1036),
                          (1330, 1036)], kind=RED, link=("dynamodb", "sns"))),
    # WAF Lambda -> SNS runs down the left side (x=1450), clear of labels
    ("edge", dict(points=[(1508, 770), (1450, 770), (1450, 985), (1354, 985),
                          (1354, 1008)], kind=RED, label="alert",
                  label_at=(1450, 880), rotate_label=True,
                  link=("waf_lambda", "sns"))),
    # Failed EventBridge deliveries -> DLQ (gray dashed)
    ("edge", dict(points=[(1568, 620), (1660, 620), (1660, 1036),
                          (1524, 1036)], kind=GRAY,
                  label="failed deliveries", label_at=(1670, 830),
                  rotate_label=True, dashed=True,
                  link=("eventbridge", "sqs"))),

    # ---- legend ----------------------------------------------------------
    ("legend", dict(x=30, y=1060)),
]


class Svg:
    """Minimal SVG builder. Coordinates are hand-placed; see DRAW."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.parts = []
        self._icon_cache = {}

    def add(self, s):
        self.parts.append(s)

    def box(self, x, y, w, h, label, fill, stroke, label_size=14, rx=10,
            label_pos="top"):
        self.add(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
        )
        ly = y + 22 if label_pos == "top" else y + h - 12
        self.add(
            f'<text x="{x + 12}" y="{ly}" font-size="{label_size}" '
            f'font-weight="600" fill="#334155">{label}</text>'
        )

    def text(self, x, y, text, size=13, weight="400", fill="#334155",
             anchor="start"):
        self.add(
            f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}">{text}</text>'
        )

    def node(self, x, y, size, icon, label, sub=None):
        cx = x + size / 2
        uri = self._icon(icon)
        self.add(
            f'<image x="{x}" y="{y}" width="{size}" height="{size}" '
            f'href="{uri}" xlink:href="{uri}"/>'
        )
        if label:
            self.add(
                f'<text x="{cx}" y="{y + size + 16}" text-anchor="middle" '
                f'font-size="12.5" font-weight="600" fill="#1e293b">{label}</text>'
            )
        if sub:
            self.add(
                f'<text x="{cx}" y="{y + size + 32}" text-anchor="middle" '
                f'font-size="11" fill="#64748b">{sub}</text>'
            )

    def text_box(self, x, y, w, h, label):
        self.add(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" '
            f'fill="#f1f5f9" stroke="#94a3b8" stroke-width="1.5"/>'
        )
        self.add(
            f'<text x="{x + w / 2}" y="{y + h / 2 + 5}" text-anchor="middle" '
            f'font-size="13" font-weight="600" fill="#334155">{label}</text>'
        )

    def edge(self, points, color, label=None, label_at=None, dashed=False,
             width=2, rotate_label=False, arrow=True):
        pts = " ".join(f"{x},{y}" for x, y in points)
        dash = ' stroke-dasharray="7,5"' if dashed else ""
        marker = f' marker-end="url(#arr-{color[1:]})"' if arrow else ""
        self.add(
            f'<polyline points="{pts}" fill="none" stroke="{color}" '
            f'stroke-width="{width}"{dash}{marker}/>'
        )
        if label:
            lx, ly = label_at or points[len(points) // 2]
            transform = ""
            if rotate_label:
                transform = f' transform="rotate(-90 {lx} {ly})"'
            self.add(
                f'<text x="{lx}" y="{ly}" text-anchor="middle" font-size="11" '
                f'fill="{color}" style="paint-order:stroke;stroke:#ffffff;'
                f'stroke-width:3px"{transform}>{label}</text>'
            )

    def legend(self, x, y):
        self.text(x, y, "Legend", size=14, weight="700", fill="#0f172a")
        items = [(BLUE, False, "request path"),
                 (ORANGE, False, "detection inputs"),
                 (RED, False, "automated response"),
                 (GRAY, True, "replication / failed deliveries")]
        for i, (color, dashed, label) in enumerate(items):
            ly = y + 22 + i * 22
            dash = ' stroke-dasharray="7,5"' if dashed else ""
            self.add(
                f'<line x1="{x}" y1="{ly}" x2="{x + 40}" y2="{ly}" '
                f'stroke="{color}" stroke-width="2.5"{dash}/>'
            )
            self.text(x + 50, ly + 5, label, size=12)
        self.text(x, y + 128,
                  "Deployment profile: ha \u2014 NAT Gateway per AZ, RDS Multi-AZ "
                  "(primary + standby).", size=12, fill="#64748b")
        self.text(x, y + 146,
                  "The lab profile uses a single NAT Gateway and single-AZ RDS. "
                  "DB subnets have no internet route.", size=12, fill="#64748b")
        self.text(x, y + 164,
                  "GuardDuty ingests CloudTrail, VPC flow, and Resolver DNS logs "
                  "natively; no customer log subscription is required.", size=12,
                  fill="#64748b")
        self.text(x, y + 182,
                  "Containment pauses the instance in its Auto Scaling Group before "
                  "it is isolated, so the ELB health check cannot replace it.",
                  size=12, fill="#64748b")

    def _icon(self, key):
        if key not in self._icon_cache:
            path = ICON_DIR / f"{key}.png"
            if not path.is_file():
                raise SystemExit(f"missing vendored icon: {path}")
            with open(path, "rb") as handle:
                self._icon_cache[key] = (
                    "data:image/png;base64,"
                    + base64.b64encode(handle.read()).decode()
                )
        return self._icon_cache[key]

    def render(self):
        markers = "".join(
            f'<marker id="arr-{c[1:]}" viewBox="0 0 10 10" refX="8" refY="5" '
            f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M 0 1 L 9 5 L 0 9 z" fill="{c}"/></marker>'
            for c in (BLUE, ORANGE, RED, GRAY)
        )
        body = "\n".join(self.parts)
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}">'
            f"<defs>{markers}</defs>"
            f'<rect width="{self.w}" height="{self.h}" fill="#ffffff"/>'
            "<g font-family=\"'Segoe UI',Arial,Helvetica,sans-serif\">"
            f"{body}</g></svg>"
        )


def render_svg() -> str:
    svg = Svg(1720, 1260)
    for kind, payload in DRAW:
        if kind == "node":
            svg.node(payload["x"], payload["y"], payload["size"],
                     payload["icon"], payload.get("label"), payload.get("sub"))
        elif kind == "text_box":
            svg.text_box(payload["x"], payload["y"], payload["w"],
                         payload["h"], payload["label"])
        elif kind == "box":
            svg.box(payload["x"], payload["y"], payload["w"], payload["h"],
                    payload["label"], payload["fill"], payload["stroke"],
                    payload.get("size", 14),
                    label_pos=payload.get("label_pos", "top"))
        elif kind == "text":
            svg.text(payload["x"], payload["y"], payload["text"],
                     size=payload.get("size", 13),
                     weight=payload.get("weight", "400"),
                     fill=payload.get("fill", "#334155"),
                     anchor=payload.get("anchor", "start"))
        elif kind == "edge":
            svg.edge(payload["points"], payload["kind"],
                     label=payload.get("label"),
                     label_at=payload.get("label_at"),
                     dashed=payload.get("dashed", False),
                     rotate_label=payload.get("rotate_label", False),
                     arrow=payload.get("arrow", True))
        elif kind == "legend":
            svg.legend(payload["x"], payload["y"])
        else:  # pragma: no cover - guarded by the model above
            raise SystemExit(f"unknown draw op: {kind}")
    return svg.render()


SHAPES = {"box": ("[", "]"), "round": ("(", ")"), "cylinder": ("[(", ")]"),
          "stadium": ("([", "])")}


def render_mermaid() -> str:
    """Emit the Mermaid view from the same model, so it cannot drift."""
    nodes = {p["id"]: p for kind, p in DRAW
             if kind in ("node", "text_box") and p.get("id")}
    children: dict[str | None, list[str]] = {}
    labels: dict[str, str] = {}
    for cid, label, parent in CONTAINERS:
        children.setdefault(parent, []).append(cid)
        labels[cid] = label

    lines = [
        "%% Generated by architecture/render.py - do not edit by hand.",
        "%% Run `python3 architecture/render.py` after any architecture change.",
        "flowchart TB",
    ]

    def node_line(node_id, payload, pad):
        opening, closing = SHAPES[payload.get("shape", "box")]
        text = payload.get("mmd") or payload.get("label") or node_id
        if payload.get("mmd") is None and payload.get("sub"):
            text = f"{text} - {payload['sub']}"
        return f'{pad}{node_id}{opening}"{text}"{closing}'

    def emit_container(cid, depth):
        pad = "  " * (depth + 1)
        lines.append(f'{pad}subgraph {cid}["{labels[cid]}"]')
        for child in children.get(cid, []):
            emit_container(child, depth + 1)
        for nid, payload in nodes.items():
            if payload.get("gid") == cid:
                lines.append(node_line(nid, payload, pad + "  "))
        lines.append(f"{pad}end")

    for root in children.get(None, []):
        emit_container(root, 0)

    for nid, payload in nodes.items():
        if payload.get("gid") not in labels:
            lines.append(node_line(nid, payload, "  "))

    lines.append("")
    styles: list[tuple[int, str]] = []
    seen: set[tuple[str, str, str | None]] = set()
    index = 0
    for kind, payload in DRAW:
        if kind != "edge" or not payload.get("link"):
            continue
        frm, to = payload["link"]
        label = payload.get("label")
        key = (frm, to, label)
        if key in seen:
            continue
        seen.add(key)
        arrow = "-.->" if payload.get("dashed") else "-->"
        if label:
            lines.append(f'  {frm} {arrow}|"{label}"| {to}')
        else:
            lines.append(f"  {frm} {arrow} {to}")
        dash = ",stroke-dasharray:7 5" if payload.get("dashed") else ""
        styles.append((index, f"stroke:{payload['kind']},stroke-width:2px{dash}"))
        index += 1

    lines.append("")
    for idx, style in styles:
        lines.append(f"  linkStyle {idx} {style}")
    return "\n".join(lines) + "\n"


def export_png(svg_text: str) -> str:
    try:
        import cairosvg
    except ImportError:
        return "cairosvg not installed; skipped PNG export"
    cairosvg.svg2png(bytestring=svg_text.encode(), write_to=str(PNG_OUT),
                     output_width=6880)
    return f"wrote {PNG_OUT.name} ({PNG_OUT.stat().st_size} bytes)"


def main(argv):
    svg_text = render_svg()
    mmd_text = render_mermaid()

    if "--check" in argv:
        stale = []
        if not SVG_OUT.is_file() or SVG_OUT.read_text() != svg_text:
            stale.append(SVG_OUT.name)
        if not MMD_OUT.is_file() or MMD_OUT.read_text() != mmd_text:
            stale.append(MMD_OUT.name)
        if stale:
            print("architecture artifacts are stale: " + ", ".join(stale))
            print("run: python3 architecture/render.py")
            return 1
        print("architecture artifacts are up to date")
        return 0

    SVG_OUT.write_text(svg_text)
    print(f"wrote {SVG_OUT.name} ({SVG_OUT.stat().st_size} bytes)")
    MMD_OUT.write_text(mmd_text)
    print(f"wrote {MMD_OUT.name} ({MMD_OUT.stat().st_size} bytes)")
    print(export_png(svg_text))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))