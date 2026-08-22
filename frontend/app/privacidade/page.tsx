import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Política de Privacidade | ShortsFlow AI",
  description: "Política de Privacidade do ShortsFlow AI e informações sobre o uso dos Serviços de API do YouTube.",
};

export default function PrivacyPage() {
  return (
    <main className="min-h-screen bg-[#f8faf5] px-6 py-12 text-[#111815]">
      <article className="mx-auto max-w-4xl rounded-[28px] border border-black/5 bg-white p-8 shadow-sm md:p-12">
        <a href="/" className="text-sm font-bold text-[#5f8500]">← Voltar ao ShortsFlow AI</a>
        <p className="mt-8 text-xs font-bold uppercase tracking-[0.22em] text-[#75a900]">ShortsFlow AI</p>
        <h1 className="mt-3 text-4xl font-black tracking-tight md:text-5xl">Política de Privacidade</h1>
        <p className="mt-4 text-sm text-[#6d776f]">Última atualização: 22 de agosto de 2026.</p>

        <div className="mt-10 space-y-8 leading-7 text-[#303934]">
          <section>
            <h2 className="text-xl font-bold text-[#111815]">1. Quem somos</h2>
            <p className="mt-2">O ShortsFlow AI é uma plataforma operada pela R2R Marketing Digital para criação, revisão e publicação de Shorts com recursos de inteligência artificial.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">2. Dados tratados</h2>
            <p className="mt-2">Podemos tratar dados de cadastro e autenticação, informações de plano e uso, dados técnicos necessários ao funcionamento da plataforma e, quando o usuário conecta sua Conta Google/YouTube, os dados autorizados pelos escopos exibidos na tela de consentimento.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">3. Uso dos Serviços de API do YouTube</h2>
            <p className="mt-2">O ShortsFlow AI utiliza os Serviços de API do YouTube. A conexão do canal ocorre exclusivamente pelo OAuth 2.0 do Google. O ShortsFlow AI não solicita nem armazena a senha da Conta Google ou do YouTube.</p>
            <p className="mt-2">Os dados autorizados são usados para identificar o canal conectado e executar, mediante ação do usuário, funcionalidades de publicação e gerenciamento compatíveis com as permissões concedidas.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">4. Tokens e segurança</h2>
            <p className="mt-2">Tokens OAuth podem ser armazenados de forma protegida pelo tempo necessário para manter a integração solicitada pelo usuário. Aplicamos controles técnicos e organizacionais destinados a restringir o acesso não autorizado aos dados de cada conta e manter o isolamento entre perfis.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">5. Compartilhamento</h2>
            <p className="mt-2">Não vendemos dados pessoais. Dados podem ser processados por provedores essenciais de infraestrutura, autenticação, processamento de IA, pagamentos e hospedagem, estritamente para viabilizar o serviço contratado e conforme as finalidades informadas.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">6. Revogação e exclusão</h2>
            <p className="mt-2">O usuário pode desconectar o YouTube dentro da plataforma. Também pode revogar o acesso concedido ao aplicativo nas configurações de segurança da Conta Google.</p>
            <p className="mt-2">Para solicitar a exclusão de dados armazenados pelo ShortsFlow AI, consulte a página <a className="font-bold text-[#5f8500] underline" href="/exclusao-de-dados">Exclusão de Dados</a>. A exclusão de dados do ShortsFlow AI não exclui conteúdos armazenados diretamente no YouTube.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">7. Serviços e políticas de terceiros</h2>
            <p className="mt-2">Ao utilizar recursos integrados ao YouTube, o usuário também está sujeito aos <a className="font-bold text-[#5f8500] underline" href="https://www.youtube.com/t/terms" target="_blank" rel="noreferrer">Termos de Serviço do YouTube</a> e à <a className="font-bold text-[#5f8500] underline" href="https://policies.google.com/privacy" target="_blank" rel="noreferrer">Política de Privacidade do Google</a>.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">8. Direitos e contato</h2>
            <p className="mt-2">O usuário pode solicitar informações, correção ou exclusão dos dados tratados pela plataforma. Para assuntos de privacidade e suporte, utilize os canais oficiais disponibilizados pela R2R Marketing Digital.</p>
          </section>
        </div>
      </article>
    </main>
  );
}
