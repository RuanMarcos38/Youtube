import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Política de Privacidade | ShortsFlow AI",
  description: "Política de Privacidade do ShortsFlow AI para integrações com YouTube, Google e TikTok.",
};

export default function PrivacyPage() {
  return (
    <main className="min-h-screen bg-[#f8faf5] px-6 py-12 text-[#111815]">
      <article className="mx-auto max-w-4xl rounded-[28px] border border-black/5 bg-white p-8 shadow-sm md:p-12">
        <a href="/integracoes" className="text-sm font-bold text-[#5f8500]">← Voltar às integrações do ShortsFlow AI</a>
        <p className="mt-8 text-xs font-bold uppercase tracking-[0.22em] text-[#75a900]">ShortsFlow AI</p>
        <h1 className="mt-3 text-4xl font-black tracking-tight md:text-5xl">Política de Privacidade</h1>
        <p className="mt-4 text-sm text-[#6d776f]">Última atualização: 5 de setembro de 2026.</p>

        <div className="mt-10 space-y-8 leading-7 text-[#303934]">
          <section>
            <h2 className="text-xl font-bold text-[#111815]">1. Quem somos</h2>
            <p className="mt-2">O ShortsFlow AI é uma plataforma operada pela R2R Marketing Digital para criação, revisão, organização e publicação de vídeos curtos com recursos de inteligência artificial e integrações autorizadas com plataformas de terceiros.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">2. Dados tratados</h2>
            <p className="mt-2">Podemos tratar dados de cadastro e autenticação, informações de plano e uso, dados técnicos necessários ao funcionamento da plataforma e dados fornecidos pelas integrações que o próprio usuário decidir conectar.</p>
            <p className="mt-2">Quando o usuário conecta Google/YouTube ou TikTok, o ShortsFlow AI recebe somente os dados e permissões autorizados na respectiva tela oficial de consentimento OAuth.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">3. Uso dos Serviços de API do YouTube</h2>
            <p className="mt-2">O ShortsFlow AI utiliza os Serviços de API do YouTube. A conexão do canal ocorre exclusivamente pelo OAuth 2.0 do Google. O ShortsFlow AI não solicita nem armazena a senha da Conta Google ou do YouTube.</p>
            <p className="mt-2">Os dados autorizados são usados para identificar o canal conectado e executar, mediante ação do usuário, funcionalidades de consulta, publicação e gerenciamento compatíveis com as permissões concedidas.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">4. Integração com TikTok</h2>
            <p className="mt-2">O ShortsFlow AI utiliza recursos oficiais do TikTok for Developers, incluindo Login Kit e Content Posting API. Quando autorizado pelo usuário, a plataforma pode receber identificadores da conta TikTok, nome de exibição, token de acesso e permissões necessárias para iniciar publicações solicitadas pelo próprio usuário.</p>
            <p className="mt-2">Para publicação, o usuário escolhe explicitamente os vídeos, a privacidade disponibilizada pelo TikTok, opções permitidas para comentários/dueto/stitch e confirma o envio. O ShortsFlow AI não publica automaticamente sem uma ação de envio do usuário e acompanha o status até a confirmação final da plataforma.</p>
            <p className="mt-2">Se o aplicativo tiver aprovação para recursos adicionais do TikTok, como Display API, poderemos consultar dados de perfil e desempenho compatíveis com os escopos concedidos, como informações básicas do perfil e métricas de vídeos. Escopos não aprovados ou não autorizados não são utilizados.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">5. Vídeos, metadados e transferência para plataformas</h2>
            <p className="mt-2">Vídeos processados pelo ShortsFlow AI podem ser armazenados pelo tempo necessário à criação, revisão e publicação. Quando o usuário solicita uma publicação, o arquivo e os metadados selecionados podem ser enviados para YouTube ou TikTok conforme as permissões concedidas e as regras da plataforma de destino.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">6. Tokens e segurança</h2>
            <p className="mt-2">Tokens OAuth podem ser armazenados de forma protegida pelo tempo necessário para manter a integração solicitada pelo usuário. Aplicamos controles técnicos e organizacionais destinados a restringir acesso não autorizado e manter o isolamento entre perfis e áreas de trabalho.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">7. Compartilhamento</h2>
            <p className="mt-2">Não vendemos dados pessoais. Dados podem ser processados por provedores essenciais de infraestrutura, autenticação, processamento de IA, pagamentos e hospedagem, estritamente para viabilizar o serviço contratado e conforme as finalidades informadas.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">8. Revogação e exclusão</h2>
            <p className="mt-2">O usuário pode desconectar integrações dentro do ShortsFlow AI e também revogar permissões diretamente na Conta Google ou TikTok, conforme disponibilizado por cada plataforma.</p>
            <p className="mt-2">Para solicitar exclusão dos dados armazenados pelo ShortsFlow AI, consulte <a className="font-bold text-[#5f8500] underline" href="/exclusao-de-dados">Exclusão de Dados</a>. Excluir dados do ShortsFlow AI não exclui automaticamente conteúdos já publicados diretamente no YouTube ou TikTok.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">9. Serviços e políticas de terceiros</h2>
            <p className="mt-2">Ao utilizar recursos integrados, o usuário também está sujeito aos termos e políticas das plataformas conectadas.</p>
            <div className="mt-3 grid gap-2 text-sm">
              <a className="font-bold text-[#5f8500] underline" href="https://www.youtube.com/t/terms" target="_blank" rel="noreferrer">Termos de Serviço do YouTube</a>
              <a className="font-bold text-[#5f8500] underline" href="https://policies.google.com/privacy" target="_blank" rel="noreferrer">Política de Privacidade do Google</a>
              <a className="font-bold text-[#5f8500] underline" href="https://www.tiktok.com/legal/page/row/terms-of-service/en" target="_blank" rel="noreferrer">Termos de Serviço do TikTok</a>
              <a className="font-bold text-[#5f8500] underline" href="https://www.tiktok.com/legal/page/row/privacy-policy/en" target="_blank" rel="noreferrer">Política de Privacidade do TikTok</a>
            </div>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">10. Direitos e contato</h2>
            <p className="mt-2">O usuário pode solicitar informações, correção ou exclusão dos dados tratados pela plataforma. Para assuntos de privacidade e suporte, utilize os canais oficiais disponibilizados pela R2R Marketing Digital.</p>
          </section>
        </div>
      </article>
    </main>
  );
}
