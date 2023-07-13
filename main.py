import os
from typing import Optional, List
from langchain.llms.base import LLM
import g4f
from g4f import Provider

from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain

os.environ['CURL_CA_BUNDLE'] = ''


class EducationalLLM(LLM):

    @property
    def _llm_type(self) -> str:
        return "custom"

    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        out = g4f.ChatCompletion.create(model='gpt-3.5-turbo',
                                        provider=g4f.Provider.DeepAi,
                                        stream=False,
                                        messages=[
                                            {"role": "user", "content": prompt}]
                                        )
        print(out)
        if stop:
            stop_indexes = (out.find(s) for s in stop if s in out)
            min_stop = min(stop_indexes, default=-1)
            if min_stop > -1:
                out = out[:min_stop]
        return out


llm = EducationalLLM()

prompt = PromptTemplate(
    input_variables=["input"],
    template="give me {input} question to ask in an software engineering interview for python developer",
)

chain = LLMChain(llm=llm, prompt=prompt)

print(chain.run("5"))
