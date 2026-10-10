from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import urlparse

from ..config import Settings
from ..models import ChatRequest, Outlook, OutlookScenario, SourceItem
from ..utils import INDICATOR_META
from .conversation_service import ConversationService
from .data_service import DataService


SOURCE_FALLBACK_NOTICE = (
    "관련 외부 자료를 충분히 확인하지 못했습니다. 아래 설명은 현재 경제지표와 "
    "일반적인 경제 원리를 바탕으로 한 가능성입니다."
)


class ChatService:
    def __init__(
        self,
        settings: Settings,
        data_service: DataService,
        conversation_service: ConversationService,
    ) -> None:
        self.settings = settings
        self.data_service = data_service
        self.conversation_service = conversation_service

    @staticmethod
    def _fmt(value: float | None, digits: int = 2) -> str:
        if value is None:
            return "확인 불가"
        return f"{value:,.{digits}f}"

    @staticmethod
    def _shift_month(period: str, offset: int) -> str:
        absolute = int(period[:4]) * 12 + int(period[5:7]) - 1 + offset
        return f"{absolute // 12:04d}-{absolute % 12 + 1:02d}"

    def _outlook(self, months: int, summary: dict) -> Outlook:
        cpi = summary["indicators"]["cpi"]
        exchange = summary["indicators"]["exchange_rate"]
        cpi_direction = cpi["recent_3"]["change"]["direction"]
        direction_map = {"상승": "상승", "하락": "하락", "유지": "유지"}
        direction = direction_map[cpi_direction]

        signals = [
            cpi["recent_3"]["change"]["direction"],
            cpi["recent_6"]["change"]["direction"],
            exchange["recent_3"]["change"]["direction"],
        ]
        agreement = sum(signal == direction for signal in signals)
        if agreement == 3:
            confidence = "높음"
            reason = "최근 3개월과 6개월의 물가 흐름 및 환율 방향이 같은 신호를 보입니다."
        elif agreement == 2:
            confidence = "보통"
            reason = "최근 흐름은 한 방향을 가리키지만 일부 지표는 다른 신호를 보입니다."
        else:
            confidence = "낮음"
            reason = "최근 지표들의 방향이 엇갈려 하나의 흐름으로 판단하기 어렵습니다."

        latest_cpi = self._fmt(cpi["latest"]["value"])
        latest_exchange = self._fmt(exchange["latest"]["value"])
        scenarios = [
            OutlookScenario(
                title="상승 시나리오",
                content=(
                    "원화 약세나 수입 비용 상승이 이어지고 서비스 가격 압력이 유지되면 "
                    "소비자물가 상승 압력이 커질 수 있습니다."
                ),
            ),
            OutlookScenario(
                title="기준 시나리오",
                content=(
                    "최근 흐름이 크게 바뀌지 않는다면 물가는 현재 수준 주변에서 완만하게 "
                    "움직일 가능성이 있습니다."
                ),
            ),
            OutlookScenario(
                title="하락 시나리오",
                content=(
                    "환율 안정, 수요 둔화 또는 원자재 가격 하락이 나타나면 물가 상승 압력이 "
                    "낮아질 수 있습니다."
                ),
            ),
        ]
        return Outlook(
            direction=direction,
            confidence=confidence,
            confidence_reason=(
                f"{reason} 최신 CPI는 {latest_cpi}, 원/달러 환율은 "
                f"{latest_exchange}입니다."
            ),
            months=months,
            watch_items=["원/달러 환율", "기준금리 결정", "국제 원자재 가격", "서비스 물가"],
            scenarios=scenarios,
        )

    @staticmethod
    def _is_outlook_question(question: str) -> bool:
        return bool(re.search(r"예측|전망|앞으로|향후|미래", question))

    @staticmethod
    def _is_investment_request(question: str) -> bool:
        return bool(
            re.search(
                r"매수|매도|사야|팔아야|투자.?추천|종목.?추천|롱|숏", question, re.I
            )
        )

    def _default_comparison(self, months: int = 6) -> dict:
        summary = self.data_service.summary()
        end_a = summary["period"]["end"]
        start_a = self._shift_month(end_a, -(months - 1))
        end_b = self._shift_month(start_a, -1)
        start_b = self._shift_month(end_b, -(months - 1))
        from ..models import Indicator

        return self.data_service.compare(
            start_a,
            end_a,
            start_b,
            end_b,
            [Indicator.exchange_rate, Indicator.base_rate, Indicator.cpi],
        )

    def _local_answer(
        self, request: ChatRequest, summary: dict, outlook: Outlook | None
    ) -> str:
        question = request.question
        if self._is_investment_request(question):
            return (
                "## 결론\n"
                "EconScope는 매수·매도나 금융상품 추천을 제공하지 않습니다. 대신 현재 "
                "경제지표가 어떤 흐름을 보이는지 설명해드릴 수 있습니다.\n\n"
                "## 근거\n"
                f"현재 분석 가능한 기간은 {summary['period']['start']}부터 "
                f"{summary['period']['end']}까지입니다. 환율·기준금리·소비자물가지수의 "
                "최근 추세와 두 기간 비교를 확인할 수 있습니다.\n\n"
                "## 주의사항\n"
                "이 서비스의 설명은 경제 학습과 정보 제공을 위한 것이며 투자 조언이 아닙니다."
            )

        cpi = summary["indicators"]["cpi"]
        exchange = summary["indicators"]["exchange_rate"]
        rate = summary["indicators"]["base_rate"]
        if request.comparison_context:
            comparison = request.comparison_context
            lines = []
            for key, result in comparison.get("indicators", {}).items():
                a = result.get("period_a", {})
                b = result.get("period_b", {})
                if not a.get("count") or not b.get("count"):
                    continue
                diff = a["average"] - b["average"]
                lines.append(
                    f"- {result['label']}: 기간 A 평균 {self._fmt(a['average'])}, "
                    f"기간 B 평균 {self._fmt(b['average'])}, 차이 {self._fmt(diff)} {result['unit']}"
                )
            return (
                "## 결론\n"
                "선택한 두 기간은 지표별로 변화 방향과 크기가 다릅니다. 가장 큰 차이는 "
                "평균뿐 아니라 기간 안의 급격한 변동 시점도 함께 봐야 합니다.\n\n"
                "## 근거 수치\n"
                + ("\n".join(lines) or "- 비교할 수 있는 관측치가 부족합니다.")
                + "\n\n## 가능한 배경\n"
                "환율은 대외 금융환경과 수급, 기준금리는 물가와 경기 판단, CPI는 수입비용과 "
                "국내 수요 등 여러 요인의 영향을 받을 수 있습니다.\n\n"
                "## 주의사항\n"
                "세 지표만으로 변화의 실제 원인을 확정할 수 없으며, 위 설명은 가능한 경제적 "
                "경로입니다."
            )

        if re.search(r"6개월|이전 6", question):
            comparison = self._default_comparison(6)
            lines = []
            for result in comparison["indicators"].values():
                a = result["period_a"]
                b = result["period_b"]
                lines.append(
                    f"- {result['label']}: 최근 평균 {self._fmt(a['average'])}, "
                    f"이전 평균 {self._fmt(b['average'])} {result['unit']}"
                )
            return (
                "## 결론\n최근 6개월과 이전 6개월의 차이를 비교했습니다. 지표마다 움직임이 "
                "달라 하나의 원인으로 설명하기는 어렵습니다.\n\n## 근거 수치\n"
                + "\n".join(lines)
                + "\n\n## 주의사항\n기간 평균은 흐름을 요약하지만 월별 급등락과 외부 충격을 "
                "모두 설명하지는 못합니다."
            )

        if outlook:
            return (
                f"## 결론\n향후 {outlook.months}개월의 물가 방향은 **{outlook.direction}**, "
                f"확신 수준은 **{outlook.confidence}**으로 봅니다. 정확한 미래 수치를 단정할 "
                "수는 없습니다.\n\n"
                "## 근거 수치\n"
                f"최신 CPI는 {self._fmt(cpi['latest']['value'])} "
                f"({cpi['latest']['date']})이며 최근 3개월 방향은 "
                f"{cpi['recent_3']['change']['direction']}입니다. 최신 환율은 "
                f"{self._fmt(exchange['latest']['value'])}원, 기준금리는 "
                f"{self._fmt(rate['latest']['value'])}%입니다.\n\n"
                "## 주의사항\n"
                "전망은 현재 데이터가 보여주는 방향을 시나리오로 설명한 것이며, 국제유가·경기·"
                "정책 변화에 따라 달라질 수 있습니다."
            )

        change = cpi["recent_3"]["change"]
        yoy = cpi.get("year_over_year")
        yoy_text = (
            f"전년 같은 달보다 {self._fmt(yoy['percent'])}% 변했습니다."
            if yoy and yoy.get("percent") is not None
            else "전년 동월 비교값은 확인하지 못했습니다."
        )
        answer = (
            "## 결론\n"
            f"최근 물가 흐름은 **{change['direction']}**입니다. 최신 소비자물가지수(CPI)는 "
            f"{self._fmt(cpi['latest']['value'])}이며 {yoy_text}\n\n"
            "## 근거 수치\n"
            f"분석 기간은 {summary['period']['start']}~{summary['period']['end']}입니다. "
            f"최근 3개월 CPI는 {self._fmt(cpi['recent_3']['values'][0]['value'])}에서 "
            f"{self._fmt(cpi['recent_3']['values'][-1]['value'])}로 움직였습니다. "
            f"같은 시점의 환율은 {self._fmt(exchange['latest']['value'])}원, 기준금리는 "
            f"{self._fmt(rate['latest']['value'])}%입니다.\n\n"
            "## 주의사항\n"
            "환율과 금리는 물가와 함께 움직일 수 있지만, 함께 움직였다는 사실만으로 어느 하나가 "
            "원인이라고 단정할 수 없습니다."
        )
        if request.detailed:
            answer += (
                "\n\n## 자세한 해석\n"
                f"전체 기간 CPI 평균은 {self._fmt(cpi['average'])}, 최저값은 "
                f"{self._fmt(cpi['minimum']['value'])}({cpi['minimum']['date']}), 최고값은 "
                f"{self._fmt(cpi['maximum']['value'])}({cpi['maximum']['date']})입니다. "
                "CPI 지수가 상승했다는 것은 가격 수준이 높아졌다는 뜻이며, 물가 상승률이 둔화한 "
                "것과 물가 수준이 하락한 것은 서로 다릅니다."
            )
        return answer

    def _prompt(self, request: ChatRequest, summary: dict, history: list[dict]) -> str:
        context = {
            "data_summary": summary,
            "comparison": request.comparison_context,
            "recent_conversation": history[-8:],
            "requested_outlook_months": request.outlook_months,
            "detailed": request.detailed,
        }
        return (
            "사용자 질문:\n"
            f"{request.question}\n\n"
            "서비스 데이터 문맥(JSON):\n"
            f"{json.dumps(context, ensure_ascii=False, default=str)}"
        )

    @staticmethod
    def _source_from_url(title: str, url: str) -> SourceItem:
        host = urlparse(url).netloc.replace("www.", "")
        organization = {
            "bok.or.kr": "한국은행",
            "ecos.bok.or.kr": "한국은행 ECOS",
            "kostat.go.kr": "통계청",
            "moef.go.kr": "기획재정부",
            "kdi.re.kr": "한국개발연구원(KDI)",
        }.get(host, host)
        return SourceItem(
            title=title or host,
            organization=organization,
            date=f"조회 {datetime.now().date().isoformat()}",
            url=url,
        )

    def _extract_sources(self, response: object) -> list[SourceItem]:
        try:
            payload = response.model_dump()
        except AttributeError:
            return []
        found: dict[str, SourceItem] = {}
        for item in payload.get("output", []):
            for content in item.get("content", []) or []:
                for annotation in content.get("annotations", []) or []:
                    url = annotation.get("url")
                    if url:
                        found[url] = self._source_from_url(
                            annotation.get("title", "외부 경제자료"), url
                        )
            action = item.get("action") or {}
            for source in action.get("sources", []) or []:
                url = source.get("url")
                if url:
                    found[url] = self._source_from_url(source.get("title", ""), url)
        return list(found.values())[:6]

    def _openai_answer(
        self, request: ChatRequest, summary: dict, history: list[dict]
    ) -> tuple[str, list[SourceItem]]:
        from openai import OpenAI

        client = OpenAI(api_key=self.settings.openai_api_key)
        tools = [{"type": "web_search"}] if self.settings.enable_web_search else []
        instructions = (
            "당신은 EconScope의 한국어 경제 선생님입니다. 경제 초보자에게 쉬운 말로 답하세요. "
            "반드시 '결론', '근거 수치', '주의사항' 순서를 사용하고 분석 기간과 실제 수치를 "
            "포함하세요. 데이터에서 관찰한 사실과 가능한 원인 가설을 구분하세요. 상관관계를 "
            "인과로 단정하지 마세요. 정확한 미래 수치와 매수·매도 추천은 금지합니다. 미래 질문은 "
            "상승·유지·하락 시나리오로 설명하세요. 외부 검색을 했다면 한국은행·통계청·기획재정부·"
            "KDI 등 공식 기관을 우선하고 출처가 확인된 사건만 언급하세요. 답변은 Markdown으로 "
            "작성하고 기본 답변은 600자 이내, 상세 요청은 1,300자 이내로 작성하세요."
        )
        response = client.responses.create(
            model=self.settings.openai_model,
            instructions=instructions,
            input=self._prompt(request, summary, history),
            tools=tools,
            max_output_tokens=1_000 if request.detailed else 650,
            store=False,
        )
        return response.output_text, self._extract_sources(response)

    def chat(self, request: ChatRequest) -> dict:
        summary = self.data_service.summary()
        history: list[dict] = []
        if request.conversation_id:
            history = self.conversation_service.get(request.conversation_id)["messages"]
        outlook = (
            self._outlook(request.outlook_months, summary)
            if self._is_outlook_question(request.question)
            else None
        )
        sources: list[SourceItem] = []
        source_notice: str | None = None
        generated_by = "local-analysis"

        if self.settings.openai_api_key and not self._is_investment_request(request.question):
            try:
                answer, sources = self._openai_answer(request, summary, history)
                generated_by = "openai"
                if self.settings.enable_web_search and not sources:
                    source_notice = SOURCE_FALLBACK_NOTICE
            except Exception:
                answer = self._local_answer(request, summary, outlook)
                source_notice = SOURCE_FALLBACK_NOTICE
        else:
            answer = self._local_answer(request, summary, outlook)
            if re.search(r"원인|이유|배경|왜", request.question):
                source_notice = SOURCE_FALLBACK_NOTICE

        metadata = {
            "sources": [source.model_dump() for source in sources],
            "source_notice": source_notice,
            "outlook": outlook.model_dump() if outlook else None,
            "generated_by": generated_by,
        }
        conversation = self.conversation_service.append(
            request.conversation_id,
            request.question,
            answer,
            metadata,
        )
        return {
            "conversation_id": conversation["id"],
            "title": conversation["title"],
            "answer": answer,
            "sources": sources,
            "source_notice": source_notice,
            "outlook": outlook,
            "generated_by": generated_by,
        }
