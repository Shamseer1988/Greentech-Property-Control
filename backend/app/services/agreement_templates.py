"""Rental-agreement clause templates — the bilingual (English/Arabic)
document content, assembled per generated agreement from the term
inputs the wizard collects.

Mirrors the `REPORT_REGISTRY` pattern in `services/reports.py`: a
decorator registers a template's clause-builder function under a slug.
Each clause function takes the render context and returns a clause
dict, or `None` to be skipped entirely — the mechanism behind every
conditional clause (the utilities sub-clause only appears when
electricity/water are actually included; the cancellation clause picks
one of two variants; the free-months clause is entirely absent when no
free months were granted). Clause bodies are Jinja2 templates so term
values interpolate cleanly without manual string-building in every
clause function.

`build_clauses()` is the single entry point both the preview endpoint
and the final `.docx` generator call — they consume the identical
clause list, so a preview can never show something the downloaded file
doesn't.
"""
from __future__ import annotations

from typing import Callable

from jinja2 import Template


AGREEMENT_TEMPLATE_REGISTRY: dict[str, dict] = {}

# Arabic weekday names, Python's Monday=0 convention.
ARABIC_WEEKDAYS = {
    0: "الاثنين", 1: "الثلاثاء", 2: "الأربعاء", 3: "الخميس",
    4: "الجمعة", 5: "السبت", 6: "الأحد",
}

ENGLISH_ORDINALS = [f"{n}." for n in range(1, 21)]
ARABIC_ORDINALS = [
    "أولاً", "ثانياً", "ثالثاً", "رابعاً", "خامساً", "سادساً", "سابعاً", "ثامناً",
    "تاسعاً", "عاشراً", "حادي عشر", "ثاني عشر", "ثالث عشر", "رابع عشر", "خامس عشر",
    "سادس عشر", "سابع عشر", "ثامن عشر", "تاسع عشر", "عشرون",
]


def agreement_template(slug: str, title: str, title_ar: str, party_roles: set[str],
                       description: str = ""):
    """Register a template's clause-builder function under `slug`."""

    def decorator(fn: Callable):
        AGREEMENT_TEMPLATE_REGISTRY[slug] = {
            "slug": slug, "title": title, "title_ar": title_ar,
            "party_roles": sorted(party_roles), "description": description,
            "builder": fn,
        }
        return fn

    return decorator


def list_templates(party_role: str | None = None) -> list[dict]:
    out = []
    for info in AGREEMENT_TEMPLATE_REGISTRY.values():
        if party_role and party_role not in info["party_roles"]:
            continue
        out.append({k: v for k, v in info.items() if k != "builder"})
    return sorted(out, key=lambda t: t["title"])


def build_clauses(slug: str, context: dict) -> list[dict]:
    """The ordered, numbered clause list for one agreement."""
    info = AGREEMENT_TEMPLATE_REGISTRY.get(slug)
    if info is None:
        raise KeyError(f"Unknown agreement template '{slug}'")
    raw = [c for c in info["builder"](context) if c is not None]

    clauses = []
    seq = 0
    for c in raw:
        if c.get("numbered"):
            heading_en = f"{ENGLISH_ORDINALS[seq]} {c['heading_en']}"
            heading_ar = f"{ARABIC_ORDINALS[seq]} :- {c['heading_ar']}"
            seq += 1
        else:
            heading_en, heading_ar = c.get("heading_en"), c.get("heading_ar")
        clauses.append({
            "heading_en": heading_en, "heading_ar": heading_ar,
            "body_en": c["body_en"], "body_ar": c["body_ar"],
        })
    return clauses


def _r(en: str, ar: str, **ctx) -> tuple[str, str]:
    return Template(en).render(**ctx), Template(ar).render(**ctx)


# ----------------------------------------------------------------------
# labour-camp-room-rental — parameterized from the reference sample
# ----------------------------------------------------------------------

def _lead_in(ctx: dict) -> dict:
    body_en, body_ar = _r(
        "Under this contract, the {{ tenant.role_label_en }} agrees to lease from the "
        "{{ lessor.role_label_en }} {{ rooms_description }}, at a rental value "
        "{{ 'inclusive' if electricity_included and water_included else "
        "('inclusive of electricity' if electricity_included else "
        "('inclusive of water' if water_included else 'exclusive')) }} of electricity, "
        "water and sewage.",
        "بموجب هذا العقد إتفقا الطرفان على أن يستأجر {{ tenant.role_label_ar }} من "
        "{{ lessor.role_label_ar }} {{ rooms_description_ar or rooms_description }} "
        "وبقيمة إيجارية "
        "{{ 'شاملة' if electricity_included and water_included else "
        "('شاملة الكهرباء' if electricity_included else "
        "('شاملة المياه' if water_included else 'غير شاملة')) }} "
        "الكهرباء والمياه والصرف الصحي.",
        **ctx,
    )
    return {"numbered": False, "heading_en": None, "heading_ar": None,
            "body_en": body_en, "body_ar": body_ar}


def _clause_lease_term(ctx: dict) -> dict:
    body_en, body_ar = _r(
        "The lease term is {{ contract_period_months }} months, commencing "
        "{{ start_date_str }} and ending {{ end_date_str }}, renewable for further "
        "similar periods upon the written agreement of both parties.",
        "مدة الايجار {{ contract_period_months }} شهراً تبدأ من {{ start_date_str }} "
        "وتنتهي في {{ end_date_str }} قابلة للتجديد لمدد أخرى مماثلة بموافقة الطرفين "
        "الخطية.",
        **ctx,
    )
    return {"numbered": True, "heading_en": "Lease Term", "heading_ar": "مده الايجار",
            "body_en": body_en, "body_ar": body_ar}


def _clause_rental_value(ctx: dict) -> dict:
    parts_en = [
        "The rental value for the property is set at a total amount of "
        "{{ currency }} {{ '%.2f'|format(rent_amount or 0) }}, payable to the "
        "{{ lessor.role_label_en }} by bank cheques every "
        "{{ rent_payment_frequency_months or 1 }} month(s)"
        "{{ ', in addition to a security cheque returned to the ' ~ tenant.role_label_en "
        "~ ' upon the end of the tenancy and settlement of all dues' "
        "if deposit_cheque_required else '' }}.",
        "The {{ tenant.role_label_en }} undertakes to pay the rent when due. Should "
        "payment not be made, or a cheque be returned unpaid for any reason, this "
        "contract shall be considered terminated automatically without the need for "
        "notice or a court ruling, and the {{ tenant.role_label_en }} shall remain "
        "liable for the rental value of the remaining period; the "
        "{{ lessor.role_label_en }} may also evict the {{ tenant.role_label_en }} and "
        "disconnect all utilities and services without objection from the "
        "{{ tenant.role_label_en }}.",
    ]
    parts_ar = [
        "حددت القيمة الإيجارية للعين المؤجرة بمبلغ إجمالي قدره {{ currency }} "
        "{{ '%.2f'|format(rent_amount or 0) }}، تدفع {{ lessor.role_label_ar_lam }} "
        "بموجب شيكات بنكية كل {{ rent_payment_frequency_months or 1 }} شهر"
        "{{ '، بالإضافة إلى شيك ضمان يرد إلى ' ~ tenant.role_label_ar ~ ' فور انتهاء "
        "العلاقة الإيجارية وتصفية كافة المستحقات والالتزامات' if deposit_cheque_required "
        "else '' }}.",
        "يتعهد ويلتزم {{ tenant.role_label_ar }} بالوفاء بالأجرة في موعد الاستحقاق، وفي "
        "حالة عدم السداد أو ارتداد الشيكات بدون صرفها لأي سبب يعتبر العقد مفسوخاً من "
        "تلقاء نفسه دون الحاجة إلى إنذار أو حكم قضائي، مع سداد باقي القيمة الإيجارية عن "
        "المدة الباقية، كما يحق {{ lessor.role_label_ar_lam }} إخلاء "
        "{{ tenant.role_label_ar }} من العين مع حق قطع كافة الخدمات والمرافق عنها دون "
        "إبداء أي اعتراض من {{ tenant.role_label_ar }}.",
    ]
    if ctx.get("electricity_included") or ctx.get("water_included"):
        which_en = ("electricity, water and sewage" if ctx.get("electricity_included") and ctx.get("water_included")
                   else "electricity" if ctx.get("electricity_included") else "water")
        which_ar = ("الكهرباء والمياه والصرف الصحي" if ctx.get("electricity_included") and ctx.get("water_included")
                   else "الكهرباء" if ctx.get("electricity_included") else "المياه")
        parts_en.append(f"The {{{{ lessor.role_label_en }}}} bears the cost of {which_en} "
                        "consumption for the leased premises during the term of this contract.")
        parts_ar.append(f"يتحمل {{{{ lessor.role_label_ar }}}} قيمة استهلاك {which_ar} "
                        "للعين المؤجرة خلال فترة التعاقد.")

    body_en = Template("\n\n".join(parts_en)).render(**ctx)
    body_ar = Template("\n\n".join(parts_ar)).render(**ctx)
    return {"numbered": True, "heading_en": "Rental Value", "heading_ar": "القيمه الايجارية",
            "body_en": body_en, "body_ar": body_ar}


def _clause_free_months(ctx: dict) -> dict | None:
    if not ctx.get("free_months_count"):
        return None
    mode = ctx.get("free_months_mode")
    if mode == "start":
        phrase_en = "the first {{ free_months_count }} month(s) of the lease term"
        phrase_ar = "أول {{ free_months_count }} شهر من مدة الايجار"
    elif mode == "end":
        phrase_en = "the last {{ free_months_count }} month(s) of the lease term"
        phrase_ar = "آخر {{ free_months_count }} شهر من مدة الايجار"
    else:
        phrase_en = "the following month(s): {{ free_months_specific_str }}"
        phrase_ar = "الأشهر التالية: {{ free_months_specific_str }}"
    body_en, body_ar = _r(
        f"The {{{{ lessor.role_label_en }}}} grants the {{{{ tenant.role_label_en }}}} a "
        f"rent-free period covering {phrase_en}, during which no rent is due for the "
        "leased premises.",
        f"يمنح {{{{ lessor.role_label_ar }}}} {{{{ tenant.role_label_ar }}}} فترة إعفاء "
        f"من الإيجار تغطي {phrase_ar}، لا يستحق خلالها أي إيجار عن العين المؤجرة.",
        **ctx,
    )
    return {"numbered": True, "heading_en": "Rent-Free Period", "heading_ar": "فترة الإعفاء من الإيجار",
            "body_en": body_en, "body_ar": body_ar}


def _clause_early_vacate_landlord(ctx: dict) -> dict:
    body_en, body_ar = _r(
        "Should the {{ lessor.role_label_en }} be unable to continue this tenancy "
        "relationship before its end date for reasons beyond the "
        "{{ tenant.role_label_en }}'s control (including but not limited to the "
        "{{ lessor.role_label_en }} vacating the building or the termination of the "
        "{{ lessor.role_label_en }}'s own upstream lease or ownership), the "
        "{{ lessor.role_label_en }} shall notify the {{ tenant.role_label_en }} in "
        "writing and shall return all cheques relating to the remaining contract period "
        "after the leased premises are actually handed over and vacated.",
        "في حالة تعذر استمرار {{ lessor.role_label_ar }} في هذه العلاقة الإيجارية قبل "
        "نهايتها لأسباب خارجة عن إرادة {{ tenant.role_label_ar }} (بما في ذلك على سبيل "
        "المثال لا الحصر إخلاء {{ lessor.role_label_ar }} للمبنى أو انتهاء عقده أو "
        "ملكيته الخاصة)، يلتزم {{ lessor.role_label_ar }} بإخطار "
        "{{ tenant.role_label_ar }} كتابياً، وبرد كافة الشيكات المتعلقة بباقي مدة العقد "
        "بعد إتمام التسليم الفعلي للعين وخلوها من الشواغل.",
        **ctx,
    )
    return {"numbered": True, "heading_en": "Early Vacate by the " + ctx["lessor"]["role_label_en"],
            "heading_ar": "الإخلاء المبكر من " + ctx["lessor"]["role_label_ar"],
            "body_en": body_en, "body_ar": body_ar}


def _clause_cancellation(ctx: dict) -> dict:
    if ctx.get("cancellation_mode") == "notice_months":
        n = ctx.get("cancellation_notice_months") or 1
        body_en, body_ar = _r(
            "Should the {{ tenant.role_label_en }} wish to vacate the leased premises "
            "before the end of the contract term, the {{ tenant.role_label_en }} shall "
            f"notify the {{{{ lessor.role_label_en }}}} at least {n} month(s) in advance "
            "by registered letter. The {{ lessor.role_label_en }} shall return the "
            "remaining cheques to the {{ tenant.role_label_en }} after handover and "
            "settlement of all dues.",
            "في حالة رغبة {{ tenant.role_label_ar }} في ترك العين المؤجرة وإخلائها قبل "
            f"نهاية مدة العقد، يلتزم بإخطار {{{{ lessor.role_label_ar }}}} قبل {n} شهر "
            "على الأقل من رغبته في ترك العين وذلك بكتاب بالبريد المسجل، على أن يلتزم "
            "{{ lessor.role_label_ar }} بتسليم باقي الشيكات {{ tenant.role_label_ar_lam }} "
            "بعد التسليم وسداد كافة المستحقات.",
            **ctx,
        )
    else:
        body_en, body_ar = _r(
            "Early termination of this contract by the {{ tenant.role_label_en }} is not "
            "permitted before the end of the contract period stated above; the "
            "{{ tenant.role_label_en }} remains liable for the rental value for the full "
            "remaining term regardless of actual occupancy.",
            "لا يجوز {{ tenant.role_label_ar_lam }} فسخ هذا العقد أو إنهاؤه قبل نهاية مدة "
            "العقد المذكورة أعلاه، ويبقى {{ tenant.role_label_ar }} ملتزماً بالقيمة "
            "الإيجارية عن كامل المدة المتبقية بصرف النظر عن الإشغال الفعلي.",
            **ctx,
        )
    return {"numbered": True, "heading_en": "Early Termination by the " + ctx["tenant"]["role_label_en"],
            "heading_ar": "إنهاء العقد المبكر من " + ctx["tenant"]["role_label_ar"],
            "body_en": body_en, "body_ar": body_ar}


def _clause_property_condition(ctx: dict) -> dict:
    body_en, body_ar = _r(
        "The {{ tenant.role_label_en }} acknowledges having fully inspected the leased "
        "premises and found them in sound condition, fit for use, complete with doors "
        "and windows, and free of any apparent or hidden defects, suitable for the "
        "purpose for which they are leased.",
        "يقر {{ tenant.role_label_ar }} بأنه عاين العين المؤجرة موضوع العقد المعاينة "
        "التامة النافية للجهالة، ووجد أن حالتها الراهنة سليمة وصالحة للاستعمال وكاملة "
        "الأبواب والنوافذ وخالية من أي عيوب سواء كانت ظاهرة أو خفية وصالحة للاستعمال "
        "للغرض المؤجرة من أجله.",
        **ctx,
    )
    return {"numbered": True, "heading_en": "Condition of the Property",
            "heading_ar": "حالة العقار", "body_en": body_en, "body_ar": body_ar}


def _clause_use_and_alteration(ctx: dict) -> dict:
    body_en, body_ar = _r(
        "The {{ tenant.role_label_en }} shall maintain the leased premises and use them "
        "as agreed, and shall return them at the end of the contract in the same "
        "condition as received. No alterations or modifications may be made to the "
        "building without the {{ lessor.role_label_en }}'s prior written consent; any "
        "unauthorized alteration renders the contract terminated automatically. The "
        "{{ tenant.role_label_en }} bears full legal responsibility for the conduct of "
        "any occupants entrusted with using the premises, as a joint guarantor with "
        "them.",
        "يلتزم {{ tenant.role_label_ar }} بالمحافظة على العين المؤجرة واستعمالها على "
        "النحو المتفق عليه، وفي نهاية العقد يسلمها كما استلمها في البداية. لا يجوز "
        "إحداث أي تغييرات أو تعديلات في المبنى إلا بموافقة كتابية من "
        "{{ lessor.role_label_ar }}، وفي حالة المخالفة يعتبر العقد مفسوخاً من تلقاء "
        "نفسه. يكون {{ tenant.role_label_ar }} مسؤولاً مسؤولية قانونية كاملة عن أعمال "
        "شاغلي العين المؤجرة الذين يعهد إليهم باستعمالها، بوصفه ضامناً متضامناً معهم.",
        **ctx,
    )
    return {"numbered": True, "heading_en": "Use of the Leased Premises and Alterations",
            "heading_ar": "استعمال العين المؤجرة والتغيير بها",
            "body_en": body_en, "body_ar": body_ar}


def _clause_no_subletting(ctx: dict) -> dict:
    body_en, body_ar = _r(
        "The {{ tenant.role_label_en }} may not sublet the leased premises nor assign "
        "this lease to any third party.",
        "لا يجوز {{ tenant.role_label_ar_lam }} التأجير من الباطن ولا التنازل عن الإيجار "
        "للغير.",
        **ctx,
    )
    return {"numbered": True, "heading_en": "Assignment and Subletting",
            "heading_ar": "التنازل عن الايجار والايجار من الباطن",
            "body_en": body_en, "body_ar": body_ar}


def _clause_maintenance(ctx: dict) -> dict:
    body_en, body_ar = _r(
        "The {{ tenant.role_label_en }} shall carry out all maintenance necessary for "
        "the building, including repairs to doors, windows and locks, plumbing works, "
        "air-conditioning maintenance, and repair and repainting of walls, restoring "
        "them to the condition in which they were received, before the end of the "
        "contract term. Should the premises not be handed back fit for use in that "
        "condition, the {{ tenant.role_label_en }} remains liable for the rental value "
        "until maintenance is completed and the premises are handed over to the "
        "{{ lessor.role_label_en }} in satisfactory condition.",
        "يلتزم {{ tenant.role_label_ar }} بعمل كافة أعمال الصيانة اللازمة للمبنى من "
        "تصليحات وتركيبات للأبواب والنوافذ والأقفال وأعمال السباكة وصيانة المكيفات "
        "وترميم الحوائط ودهانها وإعادتها بالحالة التي كانت عليها وقت استلامها، وذلك قبل "
        "نهاية مدة العقد. وفي حالة التأخير وعدم تسليم المبنى صالحاً للاستعمال بالحالة "
        "التي تم استلامها عليها، يلتزم {{ tenant.role_label_ar }} بالقيمة الإيجارية حتى "
        "الانتهاء من أعمال الصيانة وتسليم العين {{ lessor.role_label_ar_lam }} بحالة "
        "مرضية.",
        **ctx,
    )
    return {"numbered": True, "heading_en": "Maintenance", "heading_ar": "الصيانه",
            "body_en": body_en, "body_ar": body_ar}


def _clause_jurisdiction(ctx: dict) -> dict:
    body_en, body_ar = _r(
        "This contract is governed by the laws of the State of Qatar, and the courts of "
        "the State of Qatar shall have jurisdiction, according to the rules of subject-"
        "matter jurisdiction, over any dispute relating to this contract; any matter not "
        "addressed by this contract shall be governed by Qatari civil law.",
        "اتفق الطرفان على أن هذا العقد يخضع لأحكام القانون القطري، وأن محاكم دولة قطر هي "
        "صاحبة الاختصاص وفقاً لقواعد الاختصاص النوعي بنظر أي نزاع يتعلق بهذا العقد، "
        "وأيضاً كل ما لم يرد بشأنه نص في العقد يكون القانون المدني القطري صاحب "
        "الاختصاص.",
        **ctx,
    )
    return {"numbered": True, "heading_en": "Jurisdiction", "heading_ar": "الاختصاص",
            "body_en": body_en, "body_ar": body_ar}


def _clause_survival(ctx: dict) -> dict:
    body_en, body_ar = _r(
        "Should the {{ tenant.role_label_en }} leave the country, declare bankruptcy, "
        "close the company, or transfer its ownership to any other person, the monthly "
        "rent remains a binding obligation of the company, and the "
        "{{ lessor.role_label_en }} may claim it from the company until the end of the "
        "contract term.",
        "في حال ترك {{ tenant.role_label_ar }} البلد أو إعلان إفلاسه أو إغلاق الشركة أو "
        "نقل ملكية الشركة لأي شخص آخر، يبقى الإيجار الشهري ملزماً للشركة ويحق "
        "{{ lessor.role_label_ar_lam }} المطالبة بها حتى نهاية مدة العقد من الشركة.",
        **ctx,
    )
    return {"numbered": True, "heading_en": "Survival of Obligations",
            "heading_ar": "استمرار الالتزام", "body_en": body_en, "body_ar": body_ar}


def _clause_copies(ctx: dict) -> dict:
    body_en, body_ar = _r(
        "This contract has been drawn up in two original copies, one held by each party "
        "for use as required.",
        "حرر هذا العقد من نسختين بيد كل طرف نسخة للعمل بموجبها عند اللزوم.",
        **ctx,
    )
    return {"numbered": True, "heading_en": "Copies of the Contract",
            "heading_ar": "نسخ العقد", "body_en": body_en, "body_ar": body_ar}


@agreement_template(
    "labour-camp-room-rental", "Labour Camp Room Rental", "عقد إيجار غرف سكن عمال",
    {"client", "landlord"},
    description="A room/block rental agreement for labour accommodation, matching "
               "standard Qatari lease convention — lease term, rental value, "
               "utilities, early termination, maintenance and jurisdiction clauses.",
)
def _build_labour_camp_room_rental(ctx: dict) -> list[dict | None]:
    return [
        _lead_in(ctx),
        _clause_lease_term(ctx),
        _clause_rental_value(ctx),
        _clause_free_months(ctx),
        _clause_early_vacate_landlord(ctx),
        _clause_cancellation(ctx),
        _clause_property_condition(ctx),
        _clause_use_and_alteration(ctx),
        _clause_no_subletting(ctx),
        _clause_maintenance(ctx),
        _clause_jurisdiction(ctx),
        _clause_survival(ctx),
        _clause_copies(ctx),
    ]
