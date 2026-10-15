#!/usr/bin/env python3
"""Render architecture/sentinelaws.svg from official AWS Architecture Icons.

The icons ship with the ``diagrams`` PyPI package (official AWS icon set),
so no Graphviz or network access is needed:

    pip install diagrams
    python3 architecture/render.py

The diagram is grounded in terraform/: every node and edge corresponds to a
resource in terraform/modules/* (see the comments). Regenerate after any
architectural change and commit the SVG alongside the .mmd source.
"""
import base64
import os
import sys

ICON_ROOT = os.path.expanduser(
    "~/.local/lib/python3.12/site-packages/resources/aws"
)
# Fallback: locate the resources dir relative to the installed diagrams pkg.
if not os.path.isdir(ICON_ROOT):
    import diagrams  # noqa: E402

    cand = os.path.join(
        os.path.dirname(os.path.dirname(diagrams.__file__)),
        "resources",
        "aws",
    )
    if os.path.isdir(cand):
        ICON_ROOT = cand

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sentinelaws.svg")

# category/file for each official AWS Architecture Icon used.
ICONS = {
    "route53": "network/route-53.png",
    "waf": "security/waf.png",
    "acm": "security/certificate-manager.png",
    "igw": "network/internet-gateway.png",
    "alb": "network/elb-application-load-balancer.png",
    "nat": "network/nat-gateway.png",
    "ec2": "compute/ec2-instance.png",
    "rds": "database/rds-postgresql-instance.png",
    "flowlogs": "network/vpc-flow-logs.png",
    "cloudtrail": "management/cloudtrail.png",
    "config": "management/config.png",
    "s3": "storage/simple-storage-service-s3-bucket.png",
    "cloudwatch": "management/cloudwatch-logs.png",
    "guardduty": "security/guardduty.png",
    "sechub": "security/security-hub.png",
    "eventbridge": "integration/eventbridge.png",
    "lambda": "compute/lambda.png",
    "ipset": "security/waf-filtering-rule.png",
    "dynamodb": "database/dynamodb.png",
    "sns": "integration/simple-notification-service-sns.png",
    "sqs": "integration/simple-queue-service-sqs.png",
}

BLUE = "#1a73e8"  # request path
ORANGE = "#e67e22"  # detection inputs
RED = "#c0392b"  # automated response
GRAY = "#7f8c8d"  # async / replication


def data_uri(path):
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


class Svg:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.parts = []

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

    def node(self, x, y, size, icon, label, sub=None, label_anchor="middle",
             label_dx=0):
        cx = x + size / 2
        uri = data_uri(os.path.join(ICON_ROOT, ICONS[icon]))
        self.add(
            f'<image x="{x}" y="{y}" width="{size}" height="{size}" '
            f'href="{uri}" xlink:href="{uri}"/>'
        )
        lx = cx + label_dx
        anchor = label_anchor
        self.add(
            f'<text x="{lx}" y="{y + size + 16}" text-anchor="{anchor}" '
            f'font-size="12.5" font-weight="600" fill="#1e293b">{label}</text>'
        )
        if sub:
            self.add(
                f'<text x="{lx}" y="{y + size + 32}" text-anchor="{anchor}" '
                f'font-size="11" fill="#64748b">{sub}</text>'
            )
        return cx, y + size / 2

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

    def render(self):
        markers = "".join(
            f'<marker id="arr-{c[1:]}" viewBox="0 0 10 10" refX="8" refY="5" '
            f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M 0 1 L 9 5 L 0 9 z" fill="{c}"/></marker>'
            for c in (BLUE, ORANGE, RED, GRAY)
        )
        body = "\n".join(self.parts)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}">'
            f"<defs>{markers}</defs>"
            f'<rect width="{self.w}" height="{self.h}" fill="#ffffff"/>'
            f'<g font-family="\'Segoe UI\',Arial,Helvetica,sans-serif">{body}</g>'
            "</svg>"
        )


def main():
    missing = [v for v in ICONS.values()
               if not os.path.isfile(os.path.join(ICON_ROOT, v))]
    if missing:
        sys.exit(f"missing official icons: {missing}\nICON_ROOT={ICON_ROOT}")

    s = Svg(1720, 1260)

    # ---- title ----
    s.add('<text x="30" y="42" font-size="22" font-weight="700" fill="#0f172a">'
          "SentinelAWS \u2014 Architecture (hardened / HA deployment profile)</text>")
    # (No subtitle inside the image: the source/regeneration note lives in
    # the README, and the line collided with the VPC box top edge.)

    # ---- left edge: internet ----
    s.text_box(30, 95, 130, 60, "Internet users")
    s.node(198, 93, 64, "route53", "Route 53", "DNS")
    s.node(198, 238, 64, "waf", "AWS WAF", "Web ACL on ALB")
    s.node(63, 238, 64, "acm", "ACM", "TLS certificate")

    # ---- VPC ----
    s.box(350, 60, 800, 940, "VPC \u2014 DNS support + hostnames enabled",
          "#f8fafc", "#94a3b8")
    s.node(390, 100, 48, "igw", "", None)
    s.add('<text x="414" y="170" text-anchor="middle" font-size="12" '
          'font-weight="600" fill="#1e293b">Internet Gateway</text>')

    # AZ columns (terraform: networking module, 2 AZs from var.availability_zones)
    s.box(370, 185, 370, 785, "Availability Zone A", "#ffffff", "#cbd5e1",
          label_pos="bottom")
    s.box(760, 185, 370, 785, "Availability Zone B", "#ffffff", "#cbd5e1",
          label_pos="bottom")

    # Public subnets: ALB + NAT (terraform: aws_lb in public subnets,
    # aws_nat_gateway in public subnets, per-AZ in ha profile)
    s.box(385, 230, 340, 150, "Public subnets", "#eff6ff", "#bfdbfe", 12)
    s.box(775, 230, 340, 150, "Public subnets", "#eff6ff", "#bfdbfe", 12)
    s.node(719, 262, 72, "alb", "Application Load Balancer", "public \u00b7 HTTPS")
    s.node(442, 272, 56, "nat", "NAT Gateway", "AZ A")
    s.node(1012, 272, 56, "nat", "NAT Gateway", "AZ B")

    # Private app subnets: EC2 ASG (terraform: application module,
    # aws_autoscaling_group + launch template in app subnets)
    s.box(385, 405, 340, 160, "Private application subnets", "#fefce8",
          "#fde68a", 12)
    s.box(775, 405, 340, 160, "Private application subnets", "#fefce8",
          "#fde68a", 12)
    s.node(442, 452, 56, "ec2", "", None)
    s.node(552, 452, 56, "ec2", "", None)
    s.node(832, 452, 56, "ec2", "", None)
    s.node(942, 452, 56, "ec2", "", None)
    s.add('<text x="470" y="552" text-anchor="middle" font-size="12" '
          'font-weight="600" fill="#1e293b">EC2 Auto Scaling Group</text>')
    s.add('<text x="880" y="552" text-anchor="middle" font-size="12" '
          'font-weight="600" fill="#1e293b">EC2 Auto Scaling Group</text>')

    # Isolated DB subnets: RDS Multi-AZ (terraform: database module,
    # aws_db_instance multi_az=true in ha profile, no internet route)
    s.box(385, 590, 340, 160, "Isolated DB subnets", "#f1f5f9", "#cbd5e1", 12)
    s.box(775, 590, 340, 160, "Isolated DB subnets", "#f1f5f9", "#cbd5e1", 12)
    s.node(493, 622, 64, "rds", "RDS PostgreSQL", "primary \u00b7 Multi-AZ")
    s.node(883, 622, 64, "rds", "RDS PostgreSQL", "standby")

    # VPC Flow Logs (terraform: networking module, aws_flow_log -> CloudWatch)
    s.node(727, 830, 56, "flowlogs", "VPC Flow Logs", "ALL traffic")

    # ---- right panel: detection & response ----
    # (terraform: security module -> CloudTrail, Config; detection module ->
    #  GuardDuty, Security Hub; remediation module -> Lambdas, DynamoDB, DLQs)
    s.node(1258, 100, 64, "cloudtrail", "CloudTrail", "management events")
    s.node(1258, 250, 64, "config", "AWS Config", "recorder + rules")
    s.node(1488, 150, 64, "s3", "S3", "audit bucket (encrypted)")
    s.node(1488, 300, 64, "cloudwatch", "CloudWatch", "Logs")
    s.node(1262, 400, 56, "route53", "Route 53 Resolver", "DNS query logs")
    s.node(1398, 440, 72, "guardduty", "GuardDuty",
           "S3 data events \u00b7 EBS malware")
    s.node(1258, 590, 60, "sechub", "Security Hub", "finding aggregation")
    s.node(1508, 590, 60, "eventbridge", "EventBridge", "severity \u2265 7 rule")
    s.node(1258, 740, 60, "lambda", "Quarantine Lambda", "contain EC2")
    s.node(1508, 740, 60, "lambda", "WAF block Lambda", "block attacker IP")
    s.node(1508, 880, 56, "ipset", "WAF IP set", "incident blocklist")
    s.node(1258, 880, 56, "dynamodb", "DynamoDB", "incident ledger")
    s.node(1328, 1010, 52, "sns", "SNS", "alert topic")
    s.node(1470, 1010, 52, "sqs", "SQS", "encrypted DLQs")

    # ============ request path (blue) ============
    s.edge([(160, 125), (196, 125)], BLUE)
    # Route 53 -> WAF jogs right of the node labels (x=300 gutter)
    s.edge([(264, 140), (300, 140), (300, 262), (266, 262)], BLUE)
    # WAF -> IGW -> ALB (inbound). The x=320 vertical stays clear of the
    # IGW label below the icon.
    s.edge([(264, 270), (320, 270), (320, 124), (388, 124)], BLUE)
    s.edge([(440, 124), (755, 124), (755, 260)], BLUE, "inbound",
           label_at=(600, 114))
    # ACM -> ALB (TLS): routed above the public subnet bands, arrow lands on
    # the ALB icon's top edge
    s.edge([(262, 262), (320, 262), (320, 208), (730, 208), (730, 260)],
           BLUE, "TLS certificate", label_at=(610, 198))
    # ALB -> EC2 targets (private subnets). The trunk splits around the ALB
    # labels: two verticals at x=650/860, clear of the centered label strip.
    s.edge([(719, 334), (650, 334), (650, 445)], BLUE)
    s.edge([(791, 334), (860, 334), (860, 445)], BLUE)
    s.edge([(500, 445), (1000, 445)], BLUE, arrow=False)
    for x in (470, 580, 860, 970):
        s.edge([(x, 445), (x, 450)], BLUE)
    # EC2 -> RDS primary (writer endpoint). Stubs rise from the right-hand
    # instance of each AZ, join at y=578 (the gap between the subnet bands),
    # then drop into the primary's top edge.
    s.edge([(608, 510), (620, 510), (620, 578)], BLUE)
    s.edge([(998, 510), (1000, 510), (1000, 578)], BLUE)
    s.edge([(1000, 578), (550, 578), (550, 620)], BLUE)
    # RDS replication (gray dashed)
    s.edge([(589, 654), (881, 654)], GRAY, "synchronous replication",
           label_at=(735, 644), dashed=True)
    # EC2 egress via NAT -> IGW. The AZ-A vertical is offset to x=525 so it
    # does not cross the Internet Gateway label.
    s.edge([(470, 450), (470, 344)], BLUE)
    s.edge([(970, 450), (970, 400), (1040, 400), (1040, 344)], BLUE)
    s.edge([(470, 268), (525, 268), (525, 124), (442, 124)], BLUE,
           "egress via NAT", label_at=(525, 190), rotate_label=True)
    # AZ-B egress runs in the x=1110 gutter, clear of the NAT-B labels
    s.edge([(1040, 268), (1110, 268), (1110, 124), (760, 124)], BLUE)

    # ============ detection inputs (orange) ============
    # GuardDuty natively ingests CloudTrail mgmt events, VPC Flow Logs, DNS logs.
    # The CloudTrail vertical jogs to x=1385, clear of the Config labels.
    s.edge([(1360, 164), (1385, 164), (1385, 400), (1400, 400), (1400, 438)],
           ORANGE, "management events", label_at=(1385, 280),
           rotate_label=True)
    s.edge([(1392, 145), (1486, 178)], ORANGE, "audit trail",
           label_at=(1440, 148))
    s.edge([(1354, 132), (1455, 132), (1455, 332), (1486, 332)], ORANGE,
           "log delivery", label_at=(1465, 230), rotate_label=True)
    s.edge([(1324, 315), (1430, 315), (1430, 205), (1486, 205)], ORANGE,
           "configuration history", label_at=(1395, 335))
    s.edge([(783, 886), (1205, 886), (1205, 476), (1396, 476)], ORANGE,
           "VPC Flow Logs", label_at=(1215, 680), rotate_label=True)
    s.edge([(783, 865), (1420, 865), (1420, 364), (1486, 364)], ORANGE,
           "flow log delivery", label_at=(1420, 600), rotate_label=True)
    s.edge([(1320, 428), (1396, 470)], ORANGE, "DNS query logs",
           label_at=(1358, 436))

    # ============ automated response (red) ============
    s.edge([(1430, 512), (1318, 512), (1318, 588)], RED, "findings",
           label_at=(1318, 550), rotate_label=True)
    s.edge([(1470, 512), (1538, 512), (1538, 588)], RED,
           "findings (severity \u2265 7)", label_at=(1548, 550),
           rotate_label=True)
    s.edge([(1506, 650), (1318, 650), (1318, 738)], RED)
    # EventBridge -> WAF-block Lambda: routed around the right side so no
    # edge crosses the EventBridge labels.
    s.edge([(1568, 640), (1625, 640), (1625, 770), (1570, 770)], RED)
    # Quarantine Lambda acts on the EC2 instance: swap its security group
    # to the quarantine SG (terraform: remediation module,
    # ec2:ModifyNetworkInterfaceAttribute).
    s.edge([(1256, 770), (1175, 770), (1175, 498), (1028, 498)], RED,
           "swap instance security group \u2192 quarantine SG",
           label_at=(1165, 640), rotate_label=True)
    # WAF Lambda updates the WAF IP set (terraform: wafv2:UpdateIPSet on the
    # incident blocklist referenced by the ALB's Web ACL). Routed around the
    # Lambda's own label via the icon's right edge.
    s.edge([(1570, 775), (1605, 775), (1605, 908), (1566, 908)], RED,
           "wafv2:UpdateIPSet", label_at=(1618, 845), rotate_label=True)
    s.edge([(1506, 908), (1210, 908), (1210, 1020), (345, 1020), (345, 302),
            (264, 302)], RED, "blocklist enforced by Web ACL",
           label_at=(700, 1010))
    # Incident ledger + alerts (routed below the Lambdas' own labels)
    s.edge([(1270, 845), (1235, 845), (1235, 908), (1256, 908)], RED)
    s.edge([(1506, 790), (1420, 790), (1420, 908), (1316, 908)], RED,
           "incident record", label_at=(1412, 850), rotate_label=True)
    s.edge([(1320, 936), (1350, 936), (1350, 1036), (1330, 1036)], RED)
    # WAF Lambda -> SNS runs down the left side (x=1450), clear of labels
    s.edge([(1508, 770), (1450, 770), (1450, 985), (1354, 985), (1354, 1008)],
           RED, "alert", label_at=(1450, 880), rotate_label=True)
    # Failed EventBridge deliveries -> DLQ (gray dashed)
    s.edge([(1568, 620), (1660, 620), (1660, 1036), (1524, 1036)], GRAY,
           "failed deliveries", label_at=(1670, 830), rotate_label=True,
           dashed=True)

    # ---- legend ----
    lx, ly = 30, 1060
    s.add(f'<text x="{lx}" y="{ly}" font-size="14" font-weight="700" '
          f'fill="#0f172a">Legend</text>')
    items = [(BLUE, False, "request path"),
             (ORANGE, False, "detection inputs"),
             (RED, False, "automated response"),
             (GRAY, True, "replication / failed deliveries")]
    for i, (c, dashed, label) in enumerate(items):
        y = ly + 22 + i * 22
        dash = ' stroke-dasharray="7,5"' if dashed else ""
        s.add(f'<line x1="{lx}" y1="{y}" x2="{lx + 40}" y2="{y}" '
              f'stroke="{c}" stroke-width="2.5"{dash}/>')
        s.add(f'<text x="{lx + 50}" y="{y + 5}" font-size="12" '
              f'fill="#334155">{label}</text>')
    s.add(f'<text x="{lx}" y="{ly + 128}" font-size="12" fill="#64748b">'
          "Deployment profile: ha \u2014 NAT Gateway per AZ, RDS Multi-AZ "
          "(primary + standby).</text>")
    s.add(f'<text x="{lx}" y="{ly + 146}" font-size="12" fill="#64748b">'
          "The lab profile uses a single NAT Gateway and single-AZ RDS. "
          "DB subnets have no internet route.</text>")

    with open(OUT, "w") as f:
        f.write(s.render())
    print(f"wrote {OUT} ({os.path.getsize(OUT)} bytes)")

    # Optional PNG export for README embedding (renders everywhere,
    # including GitHub raw views whose CSP blocks data-URI <image>s).
    # 4x scale (6880px wide): icons render at their native 256-300px
    # resolution and text stays crisp when zoomed on high-DPI screens.
    try:
        import cairosvg

        png = os.path.splitext(OUT)[0] + ".png"
        cairosvg.svg2png(url=OUT, write_to=png, output_width=6880)
        print(f"wrote {png} ({os.path.getsize(png)} bytes)")
    except ImportError:
        print("cairosvg not installed; skipping PNG export "
              "(pip install cairosvg to enable)")


if __name__ == "__main__":
    main()
